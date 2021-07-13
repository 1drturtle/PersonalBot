import logging
import typing

from discord.ext import commands

from utils.constants import RPG_ARMY_ICON, MOD_OR_ADMIN
from utils.converters import MemberOrId
from utils.embeds import DefaultEmbed, ErrorEmbed

log = logging.getLogger(__name__)


class AmountConverter(commands.Converter):
    async def convert(self, ctx, argument: str):
        if argument.lower() == 'all':
            return 'all'
        elif argument.lower() == 'half':
            return 'half'
        elif argument.lower().strip('+-').isnumeric():
            return int(argument)
        raise commands.BadArgument()


class Item:
    def __init__(self, name: str, desc: str, cost: int, effects: dict, icon: str = ':question_mark:',
                 aliases=None):
        self.name = name
        self.aliases = aliases or []
        self.desc = desc
        self.cost = cost
        self.effects = effects
        self.icon = icon

    def amount_str(self, amount: int):
        return f'{amount}x {str(self)}'

    def __str__(self):
        return f'{self.icon} {self.name}'

    def to_dict(self):
        return {
            'name': self.name,
            'desc': self.desc,
            'cost': self.cost,
            'effects': self.effects,
            'icon': self.icon
        }

    @classmethod
    def from_dict(cls, data: dict):
        if '_id' in data:
            data.pop('_id')
        return cls(
            name=data['name'],
            desc=data['desc'],
            cost=data['cost'],
            effects=data['effects'],
            icon=data.get('icon', ':question_mark:'),
            aliases=data.get('aliases', [])
        )

    def __repr__(self):
        return f'<Item name="{self.name}", desc="{self.desc}",' \
               f' cost={self.cost}, effects={self.effects}, icon={self.icon}>'


class Inventory(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.mdb['inventory']
        self.items_db = self.bot.mdb['items']
        self.items = {}

        self.bot.loop.run_until_complete(self.load_items())

    async def load_items(self):
        item_data = await self.items_db.find().to_list(length=None)
        for raw_item in item_data:
            item = Item.from_dict(raw_item)
            self.items[item.name.lower()] = item

        log.debug('loaded items from db')

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
            item = self.items[item_name]
            items.append(f'{item_count}x **{item}**')
        embed.add_field(
            name='Items',
            value='\n'.join(items) or 'No items found.'
        )

        return await ctx.send(embed=embed)

    @inv.command(name='shop', aliases=['s'])
    async def inv_shop(self, ctx):
        """Shows a list of all items available to buy."""
        embed = DefaultEmbed(ctx)
        embed.title = 'Server Item Shop'
        out = []
        for _, item in self.items.items():
            out.append(f"- **{item}**: {item.cost} points")

        embed.description = '\n'.join(out)
        embed.add_field(name='How to Buy', value=f'You can buy an item with '
                                                 f'`{self.bot.config.PREFIX}inv buy <item name>`.')
        embed.set_thumbnail(url=RPG_ARMY_ICON)
        return await ctx.send(embed=embed)

    @inv.command(name='items', aliases=['list'])
    async def inv_item_list(self, ctx):
        """Shows a list of all items available to buy."""
        embed = DefaultEmbed(ctx)
        embed.title = 'Server Item List'
        out = []
        for _, item in self.items.items():
            out.append(f"- **{item}**: {item.desc}")

        embed.description = '\n'.join(out)
        embed.add_field(name='How to Buy', value=f'You can buy an item with '
                                                 f'`{self.bot.config.PREFIX}inv buy <item name>`.')
        embed.set_thumbnail(url=RPG_ARMY_ICON)
        return await ctx.send(embed=embed)

    @inv.command(name='buy')
    async def inv_buy(self, ctx, amount: typing.Optional[AmountConverter], *, item_name: str):
        """Buy an item from the shop."""
        if not amount:
            amount = 1

        for item in self.items:
            if item_name.lower() == item.name.lower():
                item_inst = item
                break
            else:
                for alias in item.aliases:
                    if item_name.lower() == alias.lower():
                        item_inst = item
                        break
        else:
            return await ctx.send(
                embed=ErrorEmbed(ctx,
                                 title='Item Not Found',
                                 description=f'Could not find an item with that name. '
                                             f'Check `{self.bot.config.PREFIX}inv items` for a list of all items.')
            )


def setup(bot):
    bot.add_cog(Inventory(bot))
