import json
import logging

import pendulum
import pymongo.errors
from discord.ext import commands
from collections import OrderedDict
from operator import itemgetter
from utils.functions import is_yes
from asyncio import TimeoutError

from utils.embeds import *

import typing

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


class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.redis = self.bot.redis_db
        self.env = self.bot.config.ENVIRONMENT

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

        if cmd in TRACKED_COMMANDS:

            def check(m):
                return m.channel.id == msg.channel.id and m.author.id == 555955826880413696 and \
                       len(m.embeds) == 0 and msg.author.name.lower() in m.content.lower()

            try:
                await self.bot.wait_for('message', check=check, timeout=3)
            except TimeoutError:
                return None

            cmd_id = str(TRACKED_COMMANDS[cmd])

            time = pendulum.now(tz=pendulum.tz.UTC)

            values = await self.redis.hgetall(str_id, encoding='utf-8')

            time_stamp = time.format('YYYY-MM_DD_HH')

            time_values = json.loads(values.get(time_stamp, '{}'))

            time_values.update(
                {cmd_id: time_values.get(cmd_id, 0) + 1}
            )

            values[time_stamp] = json.dumps(time_values)

            await self.redis.hmset_dict(str_id, values)

    @commands.group(name='stats', invoke_without_command=True)
    @commands.cooldown(3, 15, commands.BucketType.user)
    @commands.guild_only()
    async def tracked_stats(self, ctx, hours: typing.Optional[int] = 24, who: typing.Optional[discord.Member] = None):
        """
        Shows your tracked hunts!

        `hours` - Amount of hours to show in the Last X hours field. (min 1, max 48).
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

        content = await self.redis.hgetall(f'redis-tracked-{self.env}-{ctx.guild.id}:{str(who.id)}', encoding='utf-8')
        out = {k: json.loads(v) for k, v in content.items()}

        now = pendulum.now(tz=pendulum.tz.UTC)

        total_hunts = {
            'together': {'total': {}, 'last_x': {}},
            'individual': {'total': {}, 'last_x': {}}
        }

        hours = min(max(hours, 1), 48)

        for timestamp, hunts in out.items():
            time = pendulum.from_format(timestamp, 'YYYY-MM_DD_HH', tz=pendulum.tz.UTC)
            diff = time.diff(now, False).in_hours()

            for hunt_type, hunt_count in hunts.items():
                hunt_index = list(TRACKED_COMMANDS.values()).index(int(hunt_type))
                full_hunt_type = list(TRACKED_COMMANDS.keys())[hunt_index]

                h_type = 'together' if int(hunt_type) < 10 else 'individual'

                total_hunts[h_type]['total']['total'] = hunt_count + total_hunts[h_type]['total'].get('total', 0)
                total_hunts[h_type]['total'][full_hunt_type] = hunt_count + \
                                                               total_hunts[h_type]['total'].get(full_hunt_type, 0)

                if diff <= hours:
                    total_hunts[h_type]['last_x']['total'] = hunt_count + total_hunts[h_type]['last_x'].get('total', 0)
                    total_hunts[h_type]['last_x'][full_hunt_type] = hunt_count + \
                                                                    total_hunts[h_type]['last_x'].get(full_hunt_type, 0)

        embed = DefaultEmbed(ctx, title='Hunt Stats')

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

        embed.set_footer(text=embed.footer.text + ' | Use tb!optin to sign-up', icon_url=embed.footer.icon_url)

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

    @tracked_stats.command(name='owner', hidden=True)
    @commands.is_owner()
    async def owner_stats(self, ctx):
        """shows owner-only stats about the bot"""
        embed = DefaultEmbed(ctx)
        embed.title = 'Owner Debug Stats'
        embed.add_field(
            name='# of users',
            value=f"{len(await self.redis.smembers(f'opted-{self.env}'))} opted-in users."
        )
        embed.description = 'WIP'

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Tracker(bot))
