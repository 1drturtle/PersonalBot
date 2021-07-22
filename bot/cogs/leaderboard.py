import logging
import typing
from datetime import timezone

import discord
import pendulum
import pymongo
from discord.ext import commands, tasks

from utils.embeds import DefaultEmbed, SuccessEmbed, DefaultEmbedMessage
from utils.constants import ROLE_MILESTONES
from utils.functions import is_yes

import aiocron

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
        self.reset_cron = aiocron.crontab('00 00 * * MON', func=self.reset_weekly, tz=timezone.utc)

    async def cog_check(self, ctx):
        return getattr(ctx.guild, 'id', 0) in self.bot.whitelist

    def cog_unload(self):
        self.update_leaderboard.cancel()
        self.reset_cron.stop()

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

    async def reset_weekly(self):
        log.info(f'Weekly Leaderboard Reset Triggered...')
        # post weekly summary
        guild = self.bot.get_guild(self.bot.server_id)
        channel = discord.utils.find(lambda c: c.name == '📃╏announcements', guild.channels)
        embed = DefaultEmbedMessage(self.bot)
        if channel:
            # top 3 hunts/weekly
            embed.title = 'Leaderboard - End of Week Stats'
            await self.get_top_ten('hunt_weekly', f'redis-leaderboard-weekly-{self.env}')
            await self.get_top_ten('epic_weekly', f'redis-epic-leaderboard-weekly-{self.env}')
            embed.add_field(
                name='Hunts (top 3, weekly)',
                value='\n'.join([f'**#{i+1}**. {list(pair.keys())[0]} - {list(pair.values())[0]} hunts'
                                for i, pair in enumerate(self.leaderboards['hunt_weekly'])[:3]]) or 'No data.'
            )
            embed.add_field(
                name='Epic Events (top 3, weekly)',
                value='\n'.join([f'**#{i + 1}**. {list(pair.keys())[0]} - {list(pair.values())[0]} epic events'
                                 for i, pair in enumerate(self.leaderboards['epic_weekly'])[:3]]) or 'No data.'
            )
            # number of people who got hunt roles

            # number of users with weekly hunt roles
            in_role: typing.List[typing.Tuple[str, int]] = []
            for _, role in ROLE_MILESTONES.items():
                role = discord.utils.find(lambda r: r.name.lower() == role.lower(), guild.roles)
                if not role:
                    continue
                in_role.append((role.name, len(role.members)))
            embed.add_field(
                name='Weekly Milestones',
                value='\n'.join(
                    [f'**{role_name.title()}**: {count} user(s)' for role_name, count in in_role]) or 'N/A.',
                inline=False
            )

            log.info('Weekly announcement sent.')
            await channel.send(embed=embed)

        # wipe data!
        await self.redis.delete(f'redis-leaderboard-weekly-{self.env}')
        await self.redis.delete(f'redis-epic-leaderboard-weekly-{self.env}')

        await self.update_leaderboard.__call__()

        log.info(f'Weekly Leaderboard Reset Complete.')
        # remove weekly roles
        guild = self.bot.get_guild(self.bot.config.GUILD_ID)

        for role_name in ROLE_MILESTONES.values():
            role = discord.utils.find(lambda r: r.name == role_name, guild.roles)

            for member in role.members:
                try:
                    await member.remove_roles(role, reason='Weekly leaderboard reset - removing roles.')
                except:
                    log.error(f'Could not remove role {role_name} from {member}')
        log.info('All roles removed.')

    @commands.group(name='leaderboard', aliases=['top', 'lb'], invoke_without_command=True)
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

        embed.description = 'Weekly leaderboards reset on Monday at 00:00 (UTC).'
        next_reset = pendulum.now(tz=pendulum.UTC).next(pendulum.MONDAY)
        embed.description += f'\nNext reset: <t:{next_reset.int_timestamp}:R>'

        return await ctx.send(embed=embed)

    @leaderboards.command(name='points', hidden=True)
    @commands.check_any(commands.is_owner(), commands.has_role('Staff'))
    async def leaderboards_points(self, ctx):
        """Shows the top ten points in the server."""
        # get points data
        data = await self.bot.mdb['points'].find().sort('points', pymongo.DESCENDING).limit(10).to_list(None)
        embed = DefaultEmbed(
            ctx,
            title='Points Leaderboard'
        )
        out = []
        for i, item in enumerate(data):
            member = ctx.guild.get_member(item.get('_id'))
            out.append(f'**#{i+1}.** {member} - {item.get("points")} points')

        embed.add_field(
            name='Top 10 points',
            value='\n'.join(out)
        )

        return await ctx.send(embed=embed)

    @leaderboards.command(name='reset', hidden=True)
    @commands.check_any(commands.is_owner(), commands.has_role('Admin'))
    async def leaderboards_reset(self, ctx):
        """Resets the weekly leaderboards. Requires the Admin role."""

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

        await self.reset_weekly()

        return await ctx.send(
            embed=SuccessEmbed(
                ctx, title='Data Deleted.', description='Weekly leaderboard data has been reset.'
            )
        )

    @leaderboards.command(name='update', hidden=True)
    @commands.check_any(commands.is_owner(), commands.has_role('Admin'))
    async def updatelb(self, ctx):
        await self.update_leaderboard.__call__()
        return await ctx.send(
            embed=SuccessEmbed(
                ctx,
                title='Leaderboard Updated!',
                description='The leaderboard has been manually updated to include the latest stats. Please wait five'
                            'seconds to ensure the update goes through fully.'
            )
        )


def setup(bot):
    bot.add_cog(Leaderboard(bot))
