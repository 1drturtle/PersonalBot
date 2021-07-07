import typing

from discord.ext import commands

from utils.embeds import MemberEmbed
from utils.converters import MemberOrId


class Points(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.mdb['points']

    async def cog_check(self, ctx):
        return getattr(ctx.guild, 'id', 0) in self.bot.whitelist

    async def epic_hook(self, author, guild):

        if guild.id not in self.bot.whitelist:
            return

        await self.db.update_one(
            {'_id': author.id},
            {'$inc': {'points': 1}},
            upsert=True
        )

    async def get_points(self, member) -> int:
        data = await self.db.find_one({'_id': member.id})
        if data is None:
            return 0
        else:
            return data.get('points')

    @commands.command(name='points')
    async def points(self, ctx, who: typing.Optional[MemberOrId]):
        """Shows the amount of points you have. Points can be used to buy items in the shop.
        You can get points by spawning epic events. (WIP)"""

        if not who:
            who = ctx.author

        points = await self.get_points(who)

        embed = MemberEmbed(
            ctx, who,
            title=f'{who}\'s points'
        )

        embed.add_field(
            name='Points',
            value=f'{points}'
        )

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Points(bot))
