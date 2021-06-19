import json
import logging

import pendulum
from discord.ext import commands
from collections import OrderedDict
from operator import itemgetter

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

    # async def cog_check(self, ctx):
    #     return getattr(ctx.guild, 'id', 0) in self.bot.whitelist

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

    @commands.Cog.listener(name='on_message')
    async def tracker_listener(self, msg):

        if not msg.guild:
            return

        if not (msg.guild.id in self.bot.whitelist):
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

        total, last_24 = {}, {}
        total_i, last_24_i = {}, {}
        now = pendulum.now(tz=pendulum.tz.UTC)

        hours = min(max(hours, 1), 48)

        for timestamp, hunts in out.items():
            time = pendulum.from_format(timestamp, 'YYYY-MM_DD_HH', tz=pendulum.tz.UTC)
            diff = time.diff(now, False).in_hours()

            for hunt_type, hunt_count in hunts.items():
                hunt_index = list(TRACKED_COMMANDS.values()).index(int(hunt_type))
                full_hunt_type = list(TRACKED_COMMANDS.keys())[hunt_index]

                if int(hunt_type) < 10:
                    total['total'] = hunt_count + total.get('total', 0)
                    total[full_hunt_type] = hunt_count + total.get(full_hunt_type, 0)
                    if diff <= hours:
                        last_24['total'] = hunt_count + last_24.get('total', 0)
                        last_24[full_hunt_type] = hunt_count + last_24.get(full_hunt_type, 0)
                else:
                    total_i['total'] = hunt_count + total_i.get('total', 0)
                    total_i[full_hunt_type] = hunt_count + total_i.get(full_hunt_type, 0)
                    if diff <= hours:
                        last_24_i['total'] = hunt_count + last_24_i.get('total', 0)
                        last_24_i[full_hunt_type] = hunt_count + last_24_i.get(full_hunt_type, 0)

        total = OrderedDict(sorted(total.items(), key=itemgetter(1), reverse=True))
        last_24 = OrderedDict(sorted(last_24.items(), key=itemgetter(1), reverse=True))

        embed = DefaultEmbed(ctx, title='Hunt Together Stats')
        if total:
            embed.add_field(
                name='Total (together, all-time)',
                value='\n'.join([f'**RPG {x.title()}:** {y}' for x, y in total.items()]) or 'No hunts found.'
            )
            embed.add_field(
                name=f'Total (together, last {hours}h)',
                value='\n'.join([f'**RPG {x.title()}:** {y}' for x, y in last_24.items()]) or 'No hunts found.'
            )

        if total_i:
            if total:
                embed.add_field(name='\u200b', value='\u200b', inline=False)
            embed.add_field(
                name='Total (individual, all-time)',
                value='\n'.join([f'**RPG {x.title()}:** {y}' for x, y in total_i.items()]) or 'No hunts found.'
            )
            embed.add_field(
                name=f'Total (individual, last {hours}h)',
                value='\n'.join([f'**RPG {x.title()}:** {y}' for x, y in last_24_i.items()]) or 'No hunts found.'
            )

        embed.description = 'Here are your hunts stats. If there is nothing here, try hunting and checking again!'

        return await ctx.send(embed=embed)

    @commands.command(name='whitelist', hidden=True)
    @commands.is_owner()
    async def whitelist(self, ctx, guild_id: int):
        """whitelist a server to track hunts"""

        guild = self.bot.get_guild(guild_id)
        if not guild:
            return await ctx.send('could not find guild with id '+guild_id)

        await self.bot.mdb['whitelist'].update_one(
            {'_id': guild_id},
            {'$set': {'_id': guild_id}},
            upsert=True
        )

        self.bot.whitelist.add(guild_id)

        return await ctx.send(f'guild `{guild}` added to whitelist.')


def setup(bot):
    bot.add_cog(Tracker(bot))
