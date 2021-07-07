from discord.ext import commands


class Points(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.mdb['points']

    async def epic_hook(self, author, guild):

        await self.db.update_one(
            {'_id': author.id},
            {'$inc': {'points': 1}},
            upsert=True
        )


def setup(bot):
    bot.add_cog(Points(bot))
