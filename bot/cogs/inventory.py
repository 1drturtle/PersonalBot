import logging
import typing

from discord.ext import commands

from utils.constants import RPG_ARMY_ICON
from utils.converters import MemberOrId
from utils.embeds import DefaultEmbed

log = logging.getLogger(__name__)


ITEM_ICONS = {
    '1000 server xp': ':star:'
}
ITEM_DESCRIPTIONS = {
    '1000 server xp': 'Redeemable for 1,000 xp in Army Level (<@804896512051118121>)'
}


class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.mdb['inventory']

    async def load_inventory(self, who) -> typing.Dict[str, int]:
        """
        Loads the inventory for a specified user.
        :param who: Discord user to find the inventory for.
        :return: Dict of item name to quantity.
        """
        data = await self.db.find_one({
            '_id': who.id
        })

        if data:
            data.pop('_id')

        return data or {}

    async def save_inventory(self, who, inv: typing.Dict[str, int]):

        # remove items that have 0 quantity
        to_pop = {}
        for j, k in inv.copy().items():
            if k < 1:
                to_pop[j] = 0

        await self.db.update_one(
            {'_id': who.id},
            {'$set': inv},
            upsert=True
        )

        if to_pop:
            await self.db.update_one(
                {'_id': who.id},
                {'$unset': to_pop}
            )

    @commands.group(name='inventory', invoke_without_command=True, aliases=['inv', 'i'])
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
            value='\n'.join(items) or 'No items found.'
        )

        return await ctx.send(embed=embed)

    @inv.command(name='items')
    async def inv_itemlist(self, ctx):
        """Shows a list of all items."""
        embed = DefaultEmbed(ctx)
        embed.title = 'Server Item List'
        out = []
        for item, desc in ITEM_DESCRIPTIONS.items():
            out.append(f"{ITEM_ICONS.get(item) or ':question_mark:'} {item} - {desc}")

        embed.description = '\n'.join(out)
        embed.set_thumbnail(url=RPG_ARMY_ICON)
        return await ctx.send(embed=embed)

    @inv.command(name='update')
    @commands.is_owner()
    async def inv_update(self, ctx, who: typing.Optional[MemberOrId], *, update_str: str):
        """Updates a user's inventory. Admin-only."""

        if not who:
            who = ctx.author

        embed = DefaultEmbed(ctx)

        embed.title = f'Updating {who}\'s inventory'
        embed.description = f'Action done by {ctx.author}'

        inv = await self.load_inventory(who)

        out: typing.List[str] = []
        for combo in update_str.split(';'):
            item, val = combo.split(',')
            item, val = item.strip().lower(), int(val.strip())
            inv[item] = val

            out.append(f'Set {item} to {val}x')

        await self.save_inventory(who, inv)

        embed.add_field(
            name='Updated Items',
            value='\n'.join(out)
        )

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Inventory(bot))
