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
        return ctx.channel.id in self.bot.whitelist

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
                       'in all of your tracked hunts being deleted. (Respond yes/no)')

        def check(msg):
            return is_yes(msg.content) and msg.channel.id == ctx.channel.id and \
                   ctx.author.id == msg.author.id

        try:
            await self.bot.wait_for('message', check=check, timeout=20)
        except TimeoutError:
            return await ctx.send('Operation cancelled.', delete_after=10)

        await self.redis.srem(f'opted-{self.env}', str(ctx.author.id))
        await self.redis.delete(f'redis-tracked-{self.env}:{ctx.author.id}')
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

        if not (msg.channel.id in self.bot.whitelist):
            return

        str_id = f'redis-tracked-{self.env}:{str(msg.author.id)}'
        if not await self.redis.sismember(f'opted-{self.env}', str(msg.author.id)):
            return None

        if not msg.content.startswith('rpg'):
            return None

        cmd = msg.content.lower().lstrip('rpg ')

        if cmd in TRACKED_COMMANDS:
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

    @commands.command(name='stats')
    @commands.cooldown(3, 15, commands.BucketType.user)
    @commands.guild_only()
    async def tracked_stats(self, ctx, hours=24):
        """
        Shows your tracked hunts!

        `hours` - Amount of hours to show in the Last X hours field. (min 1, max 48).
        """
        
        if not await self.redis.sismember(f'opted-{self.env}', str(ctx.author.id)):
            return await ctx.send(embed=ErrorEmbed(ctx, title='Stats Error!', description='You must sign up for'
                                                                                          'tracking to display'
                                                                                          'stats.'))

        content = await self.redis.hgetall(f'redis-tracked-{self.env}:{str(ctx.author.id)}', encoding='utf-8')
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

        for x in ('together', 'individual'):
            total_hunts[x]['total'] = OrderedDict(
                sorted(total_hunts[x]['total'].items(), key=itemgetter(1), reverse=True)
            )
            total_hunts[x]['last_x'] = OrderedDict(
                sorted(total_hunts[x]['last_x'].items(), key=itemgetter(1), reverse=True)
            )

        embed = DefaultEmbed(ctx, title='Hunt Stats')

        embed.description = 'Here are your hunts stats. If there is nothing here, try hunting and checking again!'

        if total_hunts['together']['total']:
            embed.add_field(
                name='Total Hunts (together, all time)',
                value='\n'.join([f'**{x.title()}:** {y}'
                                 for x, y in total_hunts['together']['total'].items()]) or 'No hunts found.'
            )
            embed.add_field(
                name=f'Total Hunts (together, last {hours}h)',
                value='\n'.join([f'**{x.title()}:** {y}'
                                 for x, y in total_hunts['together']['last_x'].items()]) or 'No hunts found.'
            )

        if total_hunts['individual']['total']:
            if total_hunts['together']['total']:
                embed.add_field(name='\u200b', value='\u200b', inline=False)

            embed.add_field(
                name='Total Hunts (individual, all time)',
                value='\n'.join([f'**{x.title()}:** {y}'
                                 for x, y in total_hunts['individual']['total'].items()]) or 'No hunts found.'
            )
            embed.add_field(
                name=f'Total Hunts (individual, last {hours}h)',
                value='\n'.join([f'**{x.title()}:** {y}'
                                 for x, y in total_hunts['individual']['last_x'].items()]) or 'No hunts found.'
            )

        return await ctx.send(embed=embed)

    @commands.command(name='whitelist', hidden=True)
    @commands.is_owner()
    async def whitelist(self, ctx, channel_id: int):
        """whitelist a server to track hunts"""

        channel = self.bot.get_channel(channel_id)
        if not channel:
            return await ctx.send('could not find channel with id ' + channel_id)

        try:
            await self.bot.mdb['whitelist'].insert_one({'_id': channel.id})
        except pymongo.errors.DuplicateKeyError:
            pass

        self.bot.whitelist.add(channel.id)
        log.info(f'[whitelist] added #{channel} ({channel.id}) to whitelist')

        return await ctx.send(f'channel `{channel}` added to whitelist.')


def setup(bot):
    bot.add_cog(Tracker(bot))
