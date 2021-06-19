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
    'hunt h t': 2,
    'ascended hunt hardmode together': 3,
    'ascended hunt h t': 3
}


class Tracker(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.redis = self.bot.redis_db

    async def cog_check(self, ctx):
        return getattr(ctx.guild, 'id', 0) in self.bot.whitelist

    @commands.command(name='optin')
    async def opt_in(self, ctx):
        """Opts-in to the RPG tracker system."""
        str_id = str(ctx.author.id)
        if await self.redis.sismember('opted', str_id):
            embed = ErrorEmbed(ctx, title='Opt-in Error', description='You have already opted-in to the program.')
            return await ctx.send(embed=embed)

        await self.redis.sadd('opted', str_id)
        embed = SuccessEmbed(ctx, title='Opted-in!', description='You have been opted-in to the RPG hunt tracker.')
        return await ctx.send(embed=embed)

    @commands.Cog.listener(name='on_message')
    async def tracker_listener(self, msg):

        if not msg.guild:
            return

        if msg.guild.id not in self.bot.whitelist:
            return

        str_id = f'redis-tracked:{str(msg.author.id)}'
        if not await self.redis.sismember('opted', str(msg.author.id)):
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
    async def tracked_stats(self, ctx):
        if not await self.redis.sismember('opted', str(ctx.author.id)):
            return await ctx.send(embed=ErrorEmbed(ctx, title='Stats Error!', description='You must sign up for'
                                                                                          'tracking to display'
                                                                                          'stats.'))

        content = await self.redis.hgetall(f'redis-tracked:{str(ctx.author.id)}', encoding='utf-8')
        out = {k: json.loads(v) for k, v in content.items()}

        total, last_24 = {}, {}
        now = pendulum.now(tz=pendulum.tz.UTC)

        for timestamp, hunts in out.items():
            time = pendulum.from_format(timestamp, 'YYYY-MM_DD_HH', tz=pendulum.tz.UTC)
            diff = time.diff(now, False).in_hours()

            for hunt_type, hunt_count in hunts.items():
                x = list(TRACKED_COMMANDS.keys())[list(TRACKED_COMMANDS.values()).index(int(hunt_type))]

                total['total'] = hunt_count + total.get('total', 0)
                total[x] = hunt_count + total.get(x, 0)
                if diff <= 24:
                    last_24['total'] = hunt_count + last_24.get('total', 0)
                    last_24[x] = hunt_count + last_24.get(x, 0)

        total = OrderedDict(sorted(total.items(), key=itemgetter(1), reverse=True))
        last_24 = OrderedDict(sorted(last_24.items(), key=itemgetter(1), reverse=True))

        embed = DefaultEmbed(ctx, title='Hunt Together Stats')
        embed.add_field(name='Total (all-time)', value='\n'.join([f'**{x.title()}:** {y}' for x, y in total.items()]))
        embed.add_field(name='Total (last 24h)', value='\n'.join([f'**{x.title()}:** {y}' for x, y in last_24.items()]))

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Tracker(bot))
