import logging
import typing
from asyncio import TimeoutError
from collections import OrderedDict
from operator import itemgetter

import discord
import pendulum
import pymongo.errors
import ujson
from discord.ext import commands

from utils.converters import MemberOrId
from utils.embeds import *
from utils.functions import is_yes

log = logging.getLogger(__name__)

TRACKED_COMMANDS = {
    'hunt together': 1,
    'hunt t': 1,
    'hunt hardmode together': 2,
    'hunt together hardmode': 2,
    'hunt h t': 2,
    'hunt t h': 2,
    'ascended hunt hardmode together': 3,
    'ascended hunt together hardmode': 3,
    'ascended hunt h t': 3,
    'ascended hunt t h': 3,
    'hunt': 10,
    'hunt hardmode': 11,
    'hunt h': 12,
    'ascended hunt hardmode': 13,
    'ascended hunt h': 14
}

EPIC_EVENTS = {
    'ultra bait': {'msg': 'Placing the ultra bait...', 'id': 101},
    'epic seed': {'msg': 'Planting the epic seed...', 'id': 102},
    'coin trumpet': {'msg': 'Summoning the coin rain...', 'id': 103}
}

MOD_OR_ADMIN = [commands.has_role('Admin'), commands.has_role('Moderator')]


class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.redis = self.bot.redis_db
        self.env = self.bot.config.ENVIRONMENT

    async def update_lb(self, lb_id, author, guild, count=1):
        member = f'{guild.id}-{author.id}'

        await self.redis.zincrby(
            lb_id,
            count,
            member
        )

    async def get_leaderboard_positions(self, guild_id, member_id, epic=False) -> tuple:
        u_id = f'{guild_id}-{member_id}'
        if not epic:
            hunt_total = await self.redis.zrevrank(f'redis-leaderboard-{self.env}', u_id)
            hunt_weekly = await self.redis.zrevrank(f'redis-leaderboard-weekly-{self.env}', u_id)
            return hunt_total, hunt_weekly

        epic_total = await self.redis.zrevrank(f'redis-epic-leaderboard-{self.env}', u_id)
        epic_weekly = await self.redis.zrevrank(f'redis-epic-leaderboard-weekly-{self.env}', u_id)
        return epic_total, epic_weekly

    async def load_hunts(self, who: discord.Member, hours: int = 12):
        """Load hunts from redis database and parse into dictionary"""
        content = await self.redis.hgetall(f'redis-tracked-{self.env}-{who.guild.id}:{str(who.id)}', encoding='utf-8')
        out = {k: ujson.loads(v) for k, v in content.items()}

        now = pendulum.now(tz=pendulum.tz.UTC)

        total_hunts = {
            'together': {'total': {}, 'last_x': {}},
            'individual': {'total': {}, 'last_x': {}},
            'epic': {'total': {}, 'last_x': {}}
        }

        hours = min(max(hours, 1), 48)

        for timestamp, hunts in out.items():
            time = pendulum.from_format(timestamp, 'YYYY-MM_DD_HH', tz=pendulum.tz.UTC)
            diff = time.diff(now, False).in_hours()

            for hunt_type, hunt_count in hunts.items():
                h_type = 'together' if int(hunt_type) < 10 else 'individual' if int(hunt_type) < 100 else 'epic' \
                    if int(hunt_type) < 200 else None
                if h_type is None:
                    continue

                type_list = TRACKED_COMMANDS if h_type != 'epic' else {x: y['id'] for x, y in EPIC_EVENTS.items()}

                hunt_index = list(type_list.values()).index(int(hunt_type))
                full_hunt_type = list(type_list.keys())[hunt_index]

                total_hunts[h_type]['total']['total'] = hunt_count + total_hunts[h_type]['total'].get('total', 0)
                total_hunts[h_type]['total'][full_hunt_type] = hunt_count + \
                                                               total_hunts[h_type]['total'].get(full_hunt_type, 0)

                if diff <= hours:
                    total_hunts[h_type]['last_x']['total'] = hunt_count + total_hunts[h_type]['last_x'].get('total', 0)
                    total_hunts[h_type]['last_x'][full_hunt_type] = hunt_count + \
                                                                    total_hunts[h_type]['last_x'].get(full_hunt_type, 0)

        return total_hunts

    async def cog_check(self, ctx):
        return getattr(ctx.guild, 'id', 0) in self.bot.whitelist

    @commands.command(name='optin')
    async def opt_in(self, ctx):
        """Opts-in to the RPG tracker system."""
        str_id = str(ctx.author.id)
        if await self.redis.sismember(f'opted-{self.env}', str_id):
            embed = ErrorEmbed(ctx, title='Opt-in Error', description='You have already opted-in to the program.')
            return await ctx.send(embed=embed)

        await self.redis.sadd(f'opted-{self.env}', str_id)
        embed = SuccessEmbed(ctx, title='Opted-in!', description='You have been opted-in to the RPG hunt tracker.')
        return await ctx.send(embed=embed)

    @commands.command(name='cleardata')
    async def clear_data(self, ctx):
        """Clears all of your data from the bot. This includes **all hunts** and the opt-in. This action is
        __**irrevocable**__. """

        await ctx.send('Are you **sure** you want to clear your data? This action is **irrevocable** and will result'
                       ' in all of your tracked hunts being deleted.\n(Respond yes/no)')

        def check(msg):
            return is_yes(msg.content) and msg.channel.id == ctx.channel.id and \
                   ctx.author.id == msg.author.id

        try:
            await self.bot.wait_for('message', check=check, timeout=20)
        except TimeoutError:
            return await ctx.send('Operation cancelled.', delete_after=10)

        await self.redis.srem(f'opted-{self.env}', str(ctx.author.id))
        await self.redis.delete(f'redis-tracked-{self.env}-{ctx.guild.id}:{ctx.author.id}')
        return await ctx.send(
            embed=SuccessEmbed(
                ctx, title='Data Cleared',
                description=f'All data for {ctx.author.name}#{ctx.author.discriminator} has been removed from the bot.'
            )
        )

    @commands.Cog.listener(name='on_message')
    async def tracker_listener(self, msg):

        if not msg.guild:
            return

        if not (msg.guild.id in self.bot.whitelist):
            return

        str_id = f'redis-tracked-{self.env}-{msg.guild.id}:{str(msg.author.id)}'
        if not await self.redis.sismember(f'opted-{self.env}', str(msg.author.id)):
            return None

        if not msg.content.lower().startswith('rpg'):
            return None

        cmd = msg.content.lower().lstrip('rpg ')
        epic_cmd = cmd.strip().lstrip('use').strip()

        time = pendulum.now(tz=pendulum.tz.UTC)
        time_stamp = time.format('YYYY-MM_DD_HH')
        in_tracked, in_epic = False, False

        if (in_tracked := cmd in TRACKED_COMMANDS) or (in_epic := epic_cmd in EPIC_EVENTS):
            values = await self.redis.hgetall(str_id, encoding='utf-8')

            time_values = ujson.loads(values.get(time_stamp, '{}'))

            if in_tracked:

                def check(m):
                    if '**Your Horse**'.lower() in m.content.lower():
                        return False
                    elif f'**{msg.author.name}** lost but'.lower() in m.content.lower():
                        return False
                    return m.channel.id == msg.channel.id and m.author.id == 555955826880413696 and \
                           len(m.embeds) == 0 and msg.author.name.lower() in m.content.lower()

                try:
                    await self.bot.wait_for('message', check=check, timeout=3)
                except TimeoutError:
                    return None

                cmd_id = str(TRACKED_COMMANDS[cmd])

                time_values.update(
                    {cmd_id: time_values.get(cmd_id, 0) + 1}
                )

                values[time_stamp] = ujson.dumps(time_values)

                # update tracked stats
                await self.redis.hmset_dict(str_id, values)
                # increment leaderboard
                leaderboard_id_total = f'redis-leaderboard-{self.env}'
                await self.update_lb(leaderboard_id_total, msg.author, msg.guild)
                leaderboard_id_weekly = f'redis-leaderboard-weekly-{self.env}'
                await self.update_lb(leaderboard_id_weekly, msg.author, msg.guild)

            elif in_epic:
                def check(m):
                    return m.channel.id == msg.channel.id and m.author.id == 555955826880413696 and \
                           len(m.embeds) == 0 and m.content.lower() == EPIC_EVENTS[epic_cmd]['msg'].lower()

                try:
                    await self.bot.wait_for('message', check=check, timeout=3)
                except TimeoutError:
                    return None

                cmd_id = str(EPIC_EVENTS[epic_cmd]['id'])

                time_values.update({
                    cmd_id: time_values.get(cmd_id, 0) + 1
                })

                values[time_stamp] = ujson.dumps(time_values)

                await self.redis.hmset_dict(str_id, values)
                # increment leaderboard
                leaderboard_id_total = f'redis-epic-leaderboard-{self.env}'
                leaderboard_id_weekly = f'redis-epic-leaderboard-weekly-{self.env}'

                await self.update_lb(leaderboard_id_total, msg.author, msg.guild)
                await self.update_lb(leaderboard_id_weekly, msg.author, msg.guild)

    @commands.group(name='stats', invoke_without_command=True)
    @commands.cooldown(3, 15, commands.BucketType.user)
    @commands.guild_only()
    async def tracked_stats(self, ctx, who: typing.Optional[MemberOrId] = None, hours: typing.Optional[int] = 12):
        """
        Shows your tracked hunts!

        `hours` - Amount of hours to show in the Last X hours field. (min 1, max 48, default 12).
        `who`- Who to look up the hunts of. If not specified, defaults to yourself
        """

        if not who:
            who = ctx.author

        if not await self.redis.sismember(f'opted-{self.env}', str(who.id)):
            if who.id == ctx.author.id:
                return await ctx.send(embed=ErrorEmbed(ctx, title='Stats Error!', description='You must sign up for '
                                                                                              'tracking to display '
                                                                                              'stats. See `tb!optin`'))
            else:
                return await ctx.send(
                    embed=ErrorEmbed(ctx, title='Stats Error!', description=f'{who.name} has not signed up for hunt'
                                                                            f' tracking.')
                )
        total_hunts = await self.load_hunts(who, hours)

        embed = MemberEmbed(ctx, who, title=f'Hunt Stats for {who.name}'
                                                if who.id != ctx.author.id else 'Hunt Stats')

        embed.description = 'Here are the hunts stats. If there is nothing here, try hunting and checking again!'

        for x in ('together', 'individual'):
            total_hunts[x]['total'] = OrderedDict(
                sorted(total_hunts[x]['total'].items(), key=itemgetter(1), reverse=True)
            )
            total_hunts[x]['last_x'] = OrderedDict(
                sorted(total_hunts[x]['last_x'].items(), key=itemgetter(1), reverse=True)
            )
            if total_hunts[x]['total']:
                if x == 'individual' and total_hunts['together']['total']:
                    embed.add_field(name='\u200b', value='\u200b', inline=False)
                embed.add_field(
                    name=f'Total Hunts ({x}, all time)',
                    value='\n'.join([f'**{x.title()}:** {y}'
                                     for x, y in total_hunts[x]['total'].items()]) or 'No hunts found.'
                )
                embed.add_field(
                    name=f'Total Hunts ({x}, last {hours}h)',
                    value='\n'.join([f'**{x.title()}:** {y}'
                                     for x, y in total_hunts[x]['last_x'].items()]) or 'No hunts found.'
                )

        # leaderboard
        leaderboard_stats = await self.get_leaderboard_positions(ctx.guild.id, who.id)
        lb_names = ['Hunts (total)', 'Hunts (weekly)', 'Epic Events (total)', 'Epic Events (weekly)']
        lb_out = []
        for i, lb_c in enumerate(leaderboard_stats):
            if lb_c is not None:
                lb_out.append(f'**{lb_names[i]}:** #{lb_c + 1}')

        if lb_out:
            embed.add_field(name='\u200b', value='\u200b', inline=False)
            embed.add_field(name='Leaderboard Positions', value='\n'.join(lb_out))

        embed.set_footer(text=embed.footer.text + ' | Use tb!optin to sign-up', icon_url=embed.footer.icon_url)

        return await ctx.send(embed=embed)

    @tracked_stats.command(name='epic')
    @commands.cooldown(3, 15, commands.BucketType.user)
    @commands.guild_only()
    async def tracked_epic(self, ctx, who: typing.Optional[MemberOrId] = None, hours: typing.Optional[int] = 12):
        """See how many tracked epic events you have

        `hours` - Amount of hours to show in the Last X hours field. (min 1, max 48, default 12).
        `who`- Who to look up the events of. If not specified, defaults to yourself
        """
        who = who or ctx.author
        if not await self.redis.sismember(f'opted-{self.env}', str(who.id)):
            if who.id == ctx.author.id:
                return await ctx.send(embed=ErrorEmbed(ctx, title='Stats Error!', description='You must sign up for '
                                                                                              'tracking to display '
                                                                                              'stats. See `tb!optin`'))
            return await ctx.send(
                embed=ErrorEmbed(ctx, title='Stats Error!', description=f'{who.name} has not signed up for hunt'
                                                                        f' tracking.')
            )

        all_data = await self.load_hunts(who, hours)
        total_epic = all_data['epic']

        embed = MemberEmbed(ctx, who, title=f'Epic Event Stats for {who.name}'
                                                                    if who.id != ctx.author.id else 'Epic Event Stats')
        embed.set_footer(text=embed.footer.text + ' | Use tb!optin to sign-up', icon_url=embed.footer.icon_url)

        if total_epic['total']:
            total_epic['total'] = OrderedDict(
                sorted(total_epic['total'].items(), key=itemgetter(1), reverse=True)
            )

            embed.add_field(
                name='Total Events (all time)',
                value='\n'.join([f'**{x.title()}:** {y}'
                                 for x, y in total_epic['total'].items()]) or 'No hunts found.'
            )
        if total_epic['last_x']:
            total_epic['last_x'] = OrderedDict(
                sorted(total_epic['last_x'].items(), key=itemgetter(1), reverse=True)
            )

            embed.add_field(
                name=f'Total Events (last {hours}h)',
                value='\n'.join([f'**{x.title()}:** {y}'
                                 for x, y in total_epic['last_x'].items()]) or 'No hunts found.'
            )

        # leaderboard
        leaderboard_stats = await self.get_leaderboard_positions(ctx.guild.id, who.id, epic=True)
        lb_names = ['Epic Events (total)', 'Epic Events (weekly)']
        lb_out = []
        for i, lb_c in enumerate(leaderboard_stats):
            if lb_c is not None:
                lb_out.append(f'**{lb_names[i]}:** #{lb_c + 1}')

        if lb_out:
            embed.add_field(name='\u200b', value='\u200b', inline=False)
            embed.add_field(name='Epic Leaderboard Positions', value='\n'.join(lb_out))

        embed.description = f'Epic Event stats for {who.name}#{who.discriminator}. If there is nothing here, I have' \
                            f' no tracked epic events.'

        return await ctx.send(embed=embed)

    @tracked_stats.command(name='whitelist', hidden=True)
    @commands.is_owner()
    async def whitelist(self, ctx, guild_id: int):
        """whitelist a server to track hunts"""

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return await ctx.send('could not find server with id ' + str(guild_id))

        try:
            await self.bot.mdb['whitelist'].insert_one({'_id': guild.id})
        except pymongo.errors.DuplicateKeyError:
            pass

        self.bot.whitelist.add(guild.id)
        log.info(f'[whitelist] added {guild} ({guild.id}) to whitelist')

        return await ctx.send(f'guild `{guild}` added to whitelist.')

    @tracked_stats.command(name='admin', hidden=True)
    @commands.check_any(commands.is_owner(), *MOD_OR_ADMIN)
    async def admin_stats(self, ctx):
        """Shows stats about the bot. Requires the Moderator or Admin role."""
        embed = DefaultEmbed(ctx)
        embed.title = 'Owner Debug Stats'
        embed.add_field(
            name='# of users',
            value=f"{len(await self.redis.smembers(f'opted-{self.env}'))} opted-in users."
        )
        embed.description = 'WIP'

        return await ctx.send(embed=embed)

    @tracked_stats.command(name='overwrite', hidden=True)
    @commands.is_owner()
    async def owner_overwrite(self, ctx, who: MemberOrId, time: str, event_type: int, amount: int):
        """
        Overwrite the amount of hunts or epic events (`event_type`) for `who` at `time` to be `amount`
        """
        user_id = f'redis-tracked-{self.env}-{ctx.guild.id}:{who.id}'
        user_data = await self.redis.hgetall(user_id, encoding='utf-8')
        try:
            pendulum.from_format(time, 'YYYY-MM_DD_HH', tz=pendulum.tz.UTC)
        except ValueError:
            raise commands.BadArgument('Invalid time string provided.')

        timed_data = ujson.loads(user_data.get(time, '{}'))
        timed_data.update(
            {str(event_type): amount}
        )

        user_data.update({time: ujson.dumps(timed_data)})
        await self.redis.hmset_dict(user_id, user_data)

        return await ctx.send(
            embed=SuccessEmbed(ctx,
                               title='Stats Updated',
                               description=f'The stats for {who.name} at `{time}` for event-type '
                                           f'`{event_type}` has been set to `{amount}`.'
                               )
        )

    @tracked_stats.command(name='lbadd', hidden=True)
    @commands.is_owner()
    async def owner_lb_add(self, ctx, who: MemberOrId, type_: str, amount: int):
        raise NotImplemented('Work in Progress!')


def setup(bot):
    bot.add_cog(Tracker(bot))
