from discord.ext import commands
import discord


class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='inventory')
    async def inv(self, ctx):
        """shows the user's inventory"""


def setup(bot):
    bot.add_cog(Inventory(bot))
