import typing

from discord.ext import commands
import discord

from utils.embeds import DefaultEmbed


ITEM_ICONS = {

}
ITEM_DESCRIPTIONS = {

}


class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.mdb['inventory']

    async def load_inventory(self, who: typing.Union[discord.Member, discord.User]) -> typing.Dict[str, int]:
        """
        Loads the inventory for a specified user.
        :param who: Discord user to find the inventory for.
        :return: Dict of item name to quantity.
        """
        data = await self.db.find_one({
            '_id': who.id
        })
        return data or {}

    @commands.command(name='inventory')
    async def inv(self, ctx):
        """shows the user's inventory"""
        embed = DefaultEmbed(ctx,
                             title=f'{ctx.author.name}\'s Inventory'
                             )

        inv = await self.load_inventory(ctx.author)
        items: typing.List[str] = []
        for item_name, item_count in inv.items():
            icon = ITEM_ICONS.get(item_name, ':question:')
            items.append(
                f'{item_count}x - {icon} {item_name}'
            )
        embed.add_field(
            name='Items',
            value='\n'.join(items)
        )

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Inventory(bot))
