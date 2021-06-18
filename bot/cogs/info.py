from discord.ext import commands

from utils.embeds import DefaultEmbed


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


def setup(bot):
    bot.add_cog(Info(bot))
