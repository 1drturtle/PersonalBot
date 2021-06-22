import logging
import typing

import discord
from discord.ext import commands, tasks

from utils.embeds import DefaultEmbed, SuccessEmbed
from utils.functions import is_yes

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
        data: typing.List[typing.Tuple[str, int]] = await self.redis.zrevrange(
            key, start=0, stop=10, withscores=True, encoding='utf-8'
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

        for lb in self.leaderboards:
            self.leaderboards[lb] = []

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
        Shows the leaderboards for hunts & epic events.
        `top` - How many people to show for each leaderboard, min 3, max 10, default 5
        """

        top = max(min(top, 10), 3)
        embed = DefaultEmbed(ctx, title=f'{self.bot.user.name} Leaderboards (Top {top})')

        for lb in self.leaderboards:
            lb_name = lb.replace('_', ' ').title()

            lb_data = []

            for index, data in enumerate(self.leaderboards[lb][:top]):
                name, hunts = tuple(data.items())[0]
                type_ = ('hunt' if 'hunt' in lb else 'event') + ('s' if hunts != 1 else '')

                lb_str = f'**#{index+1}.** {name} - {hunts} {type_}'
                lb_data.append(lb_str)

            lb_data = '\n'.join(lb_data) or 'No data found.'

            embed.add_field(
                name=lb_name,
                value=lb_data
            )
            if len(embed.fields) == 2:
                embed.add_field(name='\u200b', value='\u200b', inline=False)

        return await ctx.send(embed=embed)

    @commands.command(name='resetlb')
    @commands.check_any(commands.is_owner(), commands.has_role('Admin'))
    async def leaderboards_reset(self, ctx):
        """Resets the weekly leaderboards"""

        await ctx.send('Are you **sure** you want to clear weekly data? This action is **irrevocable** and will result'
                       ' in all weekly leaderboard data being deleted.\n(Respond yes/no)')

        def check(msg):
            return is_yes(msg.content)\
                   and msg.channel.id == ctx.channel.id and \
                   ctx.author.id == msg.author.id

        try:
            await self.bot.wait_for('message', check=check, timeout=20)
        except TimeoutError:
            return await ctx.send('Operation cancelled, data has not been deleted..', delete_after=10)

        await self.redis.delete(f'redis-leaderboard-weekly-{self.env}')
        self.leaderboards['hunt_weekly'] = []
        self.leaderboards['epic_weekly'] = []
        await self.redis.delete(f'redis-epic-leaderboard-weekly-{self.env}')

        return await ctx.send(
            embed=SuccessEmbed(
                ctx, title='Data Deleted.', description='Weekly leaderboard data has been reset.'
            )
        )

    @commands.command(name='updatelb', hidden=True)
    @commands.is_owner()
    async def updatelb(self, ctx):
        await self.update_leaderboard.__call__()


def setup(bot):
    bot.add_cog(Leaderboard(bot))
