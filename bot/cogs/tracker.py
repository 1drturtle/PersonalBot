import logging

from discord.ext import commands
import pendulum
import json

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
                {cmd_id: time_values.get(cmd_id, 0)+1}
            )

            values[time_stamp] = json.dumps(time_values)

            await self.redis.hmset_dict(str_id, values)

    @commands.command(name='stats')
    async def tracked_stats(self, ctx):
        if not await self.redis.sismember('opted', str(ctx.author.id)):
            return await ctx.send(embed=ErrorEmbed(ctx, title='Stats Error!', description='You must sign up for'
                                                                                          'tracking to display'
                                                                                          'stats.'))

        content = await self.redis.hgetall(f'redis-tracked:{str(ctx.author.id)}', encoding='utf-8')
        out = {k: json.loads(v) for k, v in content.items()}

        total, last_24 = 0, 0
        now = pendulum.now(tz=pendulum.tz.UTC)

        for timestamp, hunts in out.items():
            time = pendulum.from_format(timestamp, 'YYYY-MM_DD_HH', tz=pendulum.tz.UTC)
            diff = time.diff(now, False).in_hours()

            log.info(f'{diff=} | {timestamp=} | {hunts=}')

            for hunt_type, hunt_count in hunts.items():
                total += hunt_count
                if diff <= 24:
                    last_24 += hunt_count

        embed = DefaultEmbed(ctx, title='Hunt Stats!')
        embed.add_field(name='Total (all-time)', value=f'{total} hunt(s)')
        embed.add_field(name='Total (last 24h)', value=f'{last_24} hunt(s)')

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Tracker(bot))
