import logging
import typing

import discord
import pendulum
from discord.ext import commands, tasks

from utils.constants import RPG_ARMY_ICON, EPIC_EVENTS_CHANNEL_NAME
from utils.embeds import DefaultEmbed, ErrorEmbed
import asyncio
import time

log = logging.getLogger(__name__)


class AmountConverter(commands.Converter):
    async def convert(self, ctx, argument: str):
        if argument.lower() == 'all':
            return 'all'
        elif argument.lower() == 'half':
            return 'half'
        elif argument.lower().strip('+-').isnumeric():
            if int(argument) < 1:
                argument = '1'
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
    """Handles the inventory and shop."""
    def __init__(self, bot):
        self.bot = bot

        self.points_db = self.bot.mdb['points']

        self.cd_db = self.bot.mdb['epic_cd']
        self.epic_cd_checker.start()
        self.temp_ga_role_checker.start()

        self.db = self.bot.mdb['inventory']
        self.items_db = self.bot.mdb['items']
        self.items = {}
        self.item_mapping = {
            'temp_role': self.run_temp_perms,
            'temp_ga': self.run_ga_role,
            'xp': self.run_xp,
            'special': self.run_special
        }

        self.bot.loop.run_until_complete(self.load_items())

    async def cog_check(self, ctx):
        return getattr(ctx.guild, 'id', 0) in self.bot.whitelist

    def cog_unload(self):
        self.epic_cd_checker.stop()

    async def get_points(self, who):
        data = await self.points_db.find_one({'_id': who.id})
        if not data:
            return 0
        return data.get('points', 0)

    async def mod_points(self, who, amt):
        await self.points_db.update_one(
            {'_id': who.id},
            {'$inc': {'points': amt}},
            upsert=True
        )

    async def load_items(self):
        item_data = await self.items_db.find().to_list(length=None)
        for raw_item in item_data:
            item = Item.from_dict(raw_item)
            self.items[item.name.lower()] = item

        log.debug('loaded items from db')

    def find_item(self, user_input: str) -> typing.Optional[Item]:
        for item in self.items.values():
            if user_input.lower() == item.name.lower():
                item_inst = item
                break
            else:
                is_alias = any([user_input.lower() == alias.lower() for alias in item.aliases])
                if is_alias:
                    item_inst = item
                    break
        else:
            return None
        return item_inst

    async def load_inventory(self, who) -> typing.Dict[str, int]:
        """
        Loads the inventory for a specified user.
        :param who: Discord user to find the inventory for.
        :return: Dict of item name to quantity.
        """
        data = await self.db.find_one({
            '_id': who.id
        }) or {}

        if data:
            data.pop('_id')

        for k, v in data.copy().items():
            if v == 0:
                del data[k]

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
            item = self.items[item_name.lower()]
            items.append(f'`{item_count:02d}x -` **{item}**')
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
            if item.effects.get('shop_hide'):
                continue
            out.append(f"- **{item}**: {item.cost} points")

        embed.description = ('\n'.join(out) or 'No items in database.')
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
            out.append(f"**{item}**: {item.desc}")

        embed.description = ('\n'.join(out) or 'No items in database.')
        embed.add_field(name='How to Buy', value=f'You can buy an item with '
                                                 f'`{self.bot.config.PREFIX}inv buy <item name>`.')
        embed.add_field(name='Shortcuts', value=f"Want to type a shorter name?"
                                                f" Checkout `{ctx.prefix}inv aliases`")
        embed.set_thumbnail(url=RPG_ARMY_ICON)
        return await ctx.send(embed=embed)

    @inv.command(name='aliases')
    async def inv_list_aliases(self, ctx):
        """List aliases for server items. Aliases can be used in `buy` and `use`."""
        embed = DefaultEmbed(ctx)
        embed.title = 'Server Item Alias List'
        out = []
        for _, item in self.items.items():
            out.append(f"- **{item}**: {', '.join([f'`{x}`' for x in item.aliases]) if item.aliases else 'No aliases'}")

        embed.description = ('\n'.join(out) or 'No items in database.')
        embed.set_thumbnail(url=RPG_ARMY_ICON)
        return await ctx.send(embed=embed)

    @inv.command(name='buy')
    async def inv_buy(self, ctx, amount: typing.Optional[AmountConverter], *, item_name: str):
        """Buy an item from the shop.
        Item name must exactly match the item name or one of its aliases.
        Amount is optional, and defaults to 1."""
        # set the default amount to 1 item
        if not amount:
            amount = 1

        # find our item object from names or aliases
        item_inst = self.find_item(item_name)
        if item_inst.effects.get('shop_hide'):
            return await ctx.send(
                embed=ErrorEmbed(ctx, title='Cannot Buy Item', description='This item is not available for purchase.')
            )
        if not item_inst:
            return await ctx.send(
                embed=ErrorEmbed(ctx,
                                 title='Item Not Found',
                                 description=f'Could not find an item with that name. '
                                             f'Check `{self.bot.config.PREFIX}inv items` for a list of all items.')
            )

        # grab our user's points
        user_points = await self.get_points(ctx.author)
        max_can_buy = user_points // item_inst.cost

        # convert all and half to values
        if amount == 'all':
            amount = max_can_buy
        elif amount == 'half':
            amount = max_can_buy // 2

        # error embed if we can't buy it
        if amount > max_can_buy:
            return await ctx.send(
                embed=ErrorEmbed(
                    ctx,
                    title='Not enough points',
                    description=f'You do not have enough points to make this purchase. '
                                f'You need `{(amount * item_inst.cost) - user_points}` more point(s).'
                )
            )

        # error if we would have more than 99 items
        current_item_count = (await self.db.find_one({'_id': ctx.author.id}) or {}).get(item_inst.name, 0)
        if current_item_count + amount > 99:
            return await ctx.send(
                embed=ErrorEmbed(
                    ctx,
                    title='Too many items',
                    description='This transaction would result in more than 99 of this item type.'
                                '\nThe maximum amount of one type of item is 99.'
                )
            )

        # do the points transaction
        await self.mod_points(ctx.author, -(amount * item_inst.cost))
        # add items
        await self.db.update_one(
            {'_id': ctx.author.id},
            {'$inc': {item_inst.name: amount}},
            upsert=True
        )

        # send output
        embed = DefaultEmbed(ctx)
        embed.title = f'{ctx.author} buys {"some items" if amount != 1 else "an item"}!'
        embed.add_field(
            name='Points', value=f'{user_points - (amount * item_inst.cost)} (-{amount * item_inst.cost})'
        )
        embed.add_field(
            name='New Items', value=f'**{item_inst}** (+{amount})'
        )
        embed.add_field(
            name='How to Use',
            value=f'You can check your items with `{ctx.prefix}inv`, and can use the item with `{ctx.prefix}inv use'
                  f' <item_name>`'
        )

        return await ctx.send(embed=embed)

    @inv.command(name='use')
    async def inv_use(self, ctx, *, item_name: str):
        """Use an item from your inventory."""

        # find our item object from names or aliases
        item_inst = self.find_item(item_name)
        if item_inst is None:
            return await ctx.send(
                embed=ErrorEmbed(ctx,
                                 title='Item Not Found',
                                 description=f'Could not find an item with that name. '
                                             f'Check `{self.bot.config.PREFIX}inv items` for a list of all items.')
            )

        # do we have the item
        user_data = await self.db.find_one({'_id': ctx.author.id}) or {}
        if user_data.get(item_inst.name, 0) < 1:
            return await ctx.send(
                embed=ErrorEmbed(ctx,
                                 title='Item not in inventory',
                                 description=f'You cannot use `{item_inst.name}` '
                                             f'as you do not have one in your inventory.')
            )

        # run the specified function for the item
        # noinspection PyArgumentList
        result = await self.item_mapping[item_inst.effects.get('type')](ctx, item_inst)
        # remove item from inv on success
        if result is None or result == -1:
            await self.db.update_one(
                {'_id': ctx.author.id},
                {'$inc': {item_inst.name: -1}}
            )

    # item use functions

    async def run_xp(self, ctx, item: Item):
        raise NotImplementedError

    async def run_temp_perms(self, ctx, item: Item):
        # item: effects {duration: int (hours)}
        # mongo {_id: u_id, end_time: epoch + expire}

        now = round(time.time())
        later = now + (60 * 60 * item.effects['duration'])

        embed = DefaultEmbed(ctx)
        embed.title = 'Epic Event CD Bypass Activated!'
        embed.add_field(name='Total Duration', value=f'{item.effects["duration"]} hour(s)')
        embed.add_field(name='End Time', value=f'<t:{later}:R>')
        embed.description = f'Your CD bypass item has been activated, starting now!\n' \
                            f'Check your current boost status with {ctx.prefix}inv bypass'

        await self.cd_db.update_one(
            {'_id': ctx.author.id},
            {'$set': {'end_time': later}},
            upsert=True
        )

        ch = discord.utils.find(lambda n: n.name == EPIC_EVENTS_CHANNEL_NAME, ctx.guild.channels)
        overwrites = ch.overwrites
        u = ctx.author

        perms = overwrites.get(u, discord.PermissionOverwrite())
        perms.update(manage_messages=True)
        overwrites.update({u: perms})

        await ch.edit(overwrites=overwrites)

        await ctx.send(embed=embed)

    async def run_ga_role(self, ctx, item: Item):
        # item: effects {duration: int(hours), role_id: int}

        embed = DefaultEmbed(
            ctx,
            title='GA Extra Entries Activated!'
        )

        now = round(time.time())
        later = now + (60 * 60 * item.effects['duration'])

        await self.bot.mdb['ga_db'].update_one(
            {'_id': f'{ctx.author.id}-{item.effects.get("role_id")}'},
            {'$set': {'end_time': later}},
            upsert=True
        )

        role = ctx.guild.get_role(item.effects.get('role_id'))
        await ctx.author.add_roles(role, reason="Item bought in shop.")

        embed.add_field(name='Total Duration', value=f'{item.effects["duration"]} hour(s)')
        embed.add_field(name='End Time', value=f'<t:{later}:R>')
        embed.add_field(name='Role Acquired', value=f'You have been given the role: <@&{item.effects["role_id"]}>')

        await ctx.send(embed=embed)

        return -1

    async def run_special(self, ctx, item: Item):
        # item: effect {special: unique str, duration int(hours)}
        embed = DefaultEmbed(ctx, title='Special Item Activated!')
        now = round(time.time())
        later = now + (60 * 60 * item.effects['duration'])

        await self.bot.mdb['special_db'].update_one(
            {'_id': f'{ctx.author.id}-{item.effects.get("special")}'},
            {'$set': {'end_time': later}},
            upsert=True
        )
        embed.description = 'Your special event item has been activated!'
        embed.add_field(name='Total Duration', value=f'{item.effects["duration"]} hour(s)')
        embed.add_field(name='End Time', value=f'<t:{later}:R>')

        await ctx.send(embed=embed)
        return -1

    # noinspection PyTypeChecker
    @tasks.loop(minutes=1)
    async def epic_cd_checker(self):
        """check the users in DB epic cd every minute"""
        data = await self.cd_db.find().to_list(None)
        now = round(time.time())

        guild = self.bot.get_guild(self.bot.config.GUILD_ID)
        ch: discord.TextChannel = discord.utils.find(lambda c: c.name == EPIC_EVENTS_CHANNEL_NAME, guild.channels)
        overwrites = ch.overwrites

        for item in data:
            if item.get('end_time') < now:
                u = guild.get_member(item.get('_id'))

                perms = overwrites.get(u, discord.PermissionOverwrite())
                perms.update(manage_messages=None)

                overwrites.update({u: perms})

                if perms.is_empty():
                    overwrites.pop(u)

                await self.cd_db.delete_one({'_id': u.id})
                log.debug(f'removing epic cd bypass for {u}')

        await ch.edit(overwrites=overwrites)

    @epic_cd_checker.before_loop
    async def epic_cd_checker_before(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(1)
        log.info('Epic Event CD checker started')

    @tasks.loop(minutes=3)
    async def temp_ga_role_checker(self):
        """remove GA roles after expiration date"""
        data = await self.bot.mdb['ga_db'].find().to_list(None)
        guild = self.bot.get_guild(self.bot.config.GUILD_ID)
        now = round(time.time())

        for item in data:
            member_id, role_id = item.get('_id').split('-')
            member_id, role_id = int(member_id), int(role_id)
            role = guild.get_role(role_id)

            if not now > item.get('end_time'):
                continue

            member = guild.get_member(member_id)
            await member.remove_roles(role, reason='Role Expired.')
            log.debug(f'removing @{role.name} from {member}')
            await self.bot.mdb['ga_db'].delete_one({'_id': item.get('_id')})

        # loop in special item
        special = await self.bot.mdb['special_db'].find().to_list(None)
        for special_item in special:
            if not now > special_item.get('end_time'):
                continue

            await self.bot.mdb['special_db'].delete_one({'_id': special_item.get('_id')})

    @temp_ga_role_checker.before_loop
    async def temp_ga_role_before(self):
        await self.bot.wait_until_ready()
        await asyncio.sleep(1)
        log.info('Temp GA role checker started')

    @inv.command(name='reload')
    @commands.is_owner()
    async def inv_reload_items(self, ctx):

        self.items = {}
        await self.load_items()
        await ctx.send('items reloaded')


def setup(bot):
    bot.add_cog(Inventory(bot))
