import logging
import typing

import discord
from discord.ext import commands, tasks

from utils.embeds import DefaultEmbed

log = logging.getLogger(__name__)


class Leaderboard(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.redis = self.bot.redis_db
        self.update_leaderboard.start()
        self.leaderboards: typing.Dict[str, typing.List[typing.Dict[str, int]]] = {
            'hunt_total': [],
            'hunt_weekly': [],
            'epic_total': [],
            'epic_weekly': []
        }
        self.env = self.bot.config.ENVIRONMENT

    async def cog_check(self, ctx):
        return getattr(ctx.guild, 'id', 0) in self.bot.whitelist

    def cog_unload(self):
        self.update_leaderboard.cancel()

    async def get_top_ten(self, lb_type: str, key: str):
        data: typing.List[typing.Tuple[str, int]] = await self.redis.zrange(
            key, start=-10, stop=-1, withscores=True, encoding='utf-8'
        )

        leaderboard: typing.List[typing.Dict[str, int]] = []

        for dataset in data:
            key, count = dataset
            guild_id, member_id = key.split('-')
            guild_id, member_id = int(guild_id), int(member_id)
            guild = self.bot.get_guild(guild_id)

            try:
                member = guild.get_member(member_id)
                if member is None:
                    member = await guild.fetch_member(member_id)
            except discord.HTTPException:
                member = member_id

            leaderboard.append({str(member): count})

        self.leaderboards[lb_type] = leaderboard

    @tasks.loop(hours=1)
    async def update_leaderboard(self):
        """Updates the leaderboard from redis."""

        log.debug('updating leaderboard')

        # hunt leaderboard, total
        await self.get_top_ten('hunt_total', f'redis-leaderboard-{self.env}')
        # hunt leaderboard, weekly
        await self.get_top_ten('hunt_weekly', f'redis-leaderboard-weekly-{self.env}')
        # epic leaderboard, total
        await self.get_top_ten('epic_total', f'redis-epic-leaderboard-{self.env}')
        # epic leaderboard, weekly
        await self.get_top_ten('epic_weekly', f'redis-epic-leaderboard-weekly-{self.env}')

        log.debug(self.leaderboards)

    @update_leaderboard.before_loop
    async def leaderboard_wait_bot_ready(self):
        await self.bot.wait_until_ready()

    @commands.command(name='leaderboard', aliases=['top', 'lb'])
    @commands.cooldown(3, 10, commands.BucketType.user)
    async def leaderboards(self, ctx, top=5):
        """
        Shows the leaderboards for hunts & epic events. Weekly leaderboards are reset Monday at 00:00 UTC.
        `top` - How many people to show for each leaderboard, min 3, max 10, default 5
        """

        top = max(min(top, 10), 3)
        embed = DefaultEmbed(ctx, title=f'{self.bot.user.name} Leaderboards (Top {top})')

        for lb in self.leaderboards:
            lb_name = lb.replace('_', ' ').title()

            lb = '\n'.join(
                [f'{i+1}. '  # leaderboard position
                 f'{list(data.keys())[0]} - {list(data.values())[0]}'  # name & # of events
                 for i, data in enumerate(self.leaderboards[lb][:top+1])]
            ) or 'No records found.'

            lb = f'```\n{lb}\n```'

            embed.add_field(
                name=lb_name,
                value=lb
            )
            if len(embed.fields) == 2:
                embed.add_field(name='\u200b', value='\u200b', inline=False)

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Leaderboard(bot))
