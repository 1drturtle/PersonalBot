from discord.ext import commands

from utils.embeds import DefaultEmbed
import pendulum


class Info(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='info')
    async def info(self, ctx):
        """Shows information about the bot."""
        embed = DefaultEmbed(ctx)
        embed.title = f'{self.bot.user.name} Info'
        embed.description = self.bot.description

        embed.add_field(
            name='Stats',
            value=f'{len(self.bot.guilds)} servers'
        )

        embed.add_field(
            name='Owner',
            value='Dr Turtle#1771'
        )

        return await ctx.send(embed=embed)

    @commands.command(name='ping')
    @commands.cooldown(5, 5, type=commands.BucketType.user)
    async def ping(self, ctx):
        """Shows the latency of the bot."""
        embed = DefaultEmbed(ctx)
        # add bot ping
        embed.title = f'{self.bot.user.name} Ping'
        embed.add_field(name='Bot Ping', value=f'```fix\n{round(self.bot.latency * 1000)} ms\n```')

        # redis db ping

        t = pendulum.now()
        await self.bot.redis_db.ping()
        t2 = pendulum.now()
        redis_ping = round((t2 - t).total_seconds() * 1000)
        embed.add_field(name='Redis DB ping', value=f'```fix\n{redis_ping} ms\n```')

        # mongodb ping
        t = pendulum.now()
        await self.bot.mdb['whitelist'].find_one()
        t2 = pendulum.now()
        mongo_ping = round((t2 - t).total_seconds() * 1000)
        embed.add_field(name='MongoDB ping', value=f'```fix\n{mongo_ping} ms\n```')

        # time sending message
        websocket = pendulum.now()
        msg = await ctx.send(embed=embed)
        websocket = pendulum.now() - websocket
        # edit embed for discord ping and send
        embed.add_field(name='Discord Ping', value=f'```fix\n{round(websocket.total_seconds() * 1000)} ms\n```')
        return await msg.edit(embed=embed)

    @commands.command(name='uptime', aliases=['up', 'alive'])
    async def uptime(self, ctx):
        """Shows the uptime of the bot."""
        embed = DefaultEmbed(ctx)
        embed.title = f'{self.bot.user.name} Uptime'
        embed.add_field(name='Current Uptime', value=f'```fix\n{self.bot.uptime.in_words()}\n```')
        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Info(bot))
