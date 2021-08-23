import datetime
import logging
import re
import time
import typing

import pendulum
from discord.ext import commands

from utils.constants import EPIC_EVENTS_POINTS, POINTS_EMOJI, owner_or_mods
from utils.converters import MemberOrId
from utils.embeds import DefaultEmbedMessage, DefaultEmbed
from utils.embeds import MemberEmbed

log = logging.getLogger(__name__)


class Points(commands.Cog):
    """Cog that handles Army Points."""
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.mdb['points']

    async def cog_check(self, ctx):
        return getattr(ctx.guild, 'id', 0) in self.bot.whitelist

    async def mod_points(self, user_id: int, amount: int, multiplier: int = 1):
        # check to see if we have a boost
        boost_data = await self.bot.mdb['point_boost'].find_one({'_id': user_id})
        if boost_data:
            now = round(time.time())
            if now < boost_data.get('end_time'):
                multiplier *= boost_data.get('multiplier')
            elif now > boost_data.get('end_time'):
                await self.bot.mdb['point_boot'].delete_one({'_id': user_id})

        # update points
        await self.db.update_one(
            {'_id': user_id},
            {'$inc': {'points': amount * multiplier}},
            upsert=True
        )

        return amount * multiplier

    async def epic_hook(self, author, guild, event_type: str):

        if guild.id not in self.bot.whitelist:
            return

        await self.mod_points(author.id, amount=EPIC_EVENTS_POINTS[event_type])

    async def hunt_hook(self, msg, _):
        weekly = await self.bot.redis_db.zscore(
            f'redis-leaderboard-weekly-{self.bot.config.ENVIRONMENT}', f'{msg.guild.id}-{msg.author.id}'
        )

        if weekly is None:
            weekly = 0

        on_trigger = 100
        # do we have a special item?
        d = await self.bot.mdb['special_db'].find_one({'_id': f'{msg.author.id}-hunts'})
        if d:
            on_trigger = 15

        if weekly % on_trigger == 0 and weekly != 0:
            # if our current hunt is a multiple of 100
            # add a point depending on the current weekly hunt count
            hunt_point = 1 + (weekly >= 500) + (weekly >= 1000)

            h = await self.mod_points(msg.author.id, hunt_point)
            await msg.channel.send(embed=DefaultEmbedMessage(self.bot, title='Point Added!',
                                                             description=f'You reached {weekly} weekly hunts, and got '
                                                                         f'{h} point(s).'))

    @commands.Cog.listener(name='on_message')
    async def vote_listener(self, msg):
        if getattr(msg.guild, 'id', None) not in self.bot.whitelist:
            return

        if msg.channel.name != '🔝╏vote-us' or msg.author.id != 702134514637340702:
            return

        if len(msg.embeds):
            embed = msg.embeds[0]
        else:
            return

        mention = re.search(r'\((?P<id>\d+)\)', embed.description.lower())
        if not mention:
            return

        member = msg.guild.get_member(int(mention.group('id')))
        if not member:
            return

        await self.mod_points(member.id, 10)

        new_end = round(time.time()) + 60 * 60 * 6  # 6 hours
        await self.bot.mdb['point_boost'].update_one(
            {'_id': member.id},
            {'$set': {'multiplier': 2, 'end_time': new_end}},
            upsert=True
        )

    async def get_points(self, member) -> int:
        data = await self.db.find_one({'_id': member.id})
        if data is None:
            return 0
        else:
            return data.get('points')

    @commands.group(name='points', invoke_without_command=True)
    async def points(self, ctx, who: typing.Optional[MemberOrId]):
        """Shows the amount of points you have. Points can be used to buy items in the shop.
        You can get points by spawning epic events.
        See `tb!points help` for more information"""

        if not who:
            who = ctx.author

        points = await self.get_points(who)

        embed = MemberEmbed(
            ctx, who,
            title=f'{who}\'s points'
        )

        embed.add_field(
            name='Points',
            value=f'{POINTS_EMOJI} {points} army points'
        )

        return await ctx.send(embed=embed)

    @points.command(name='help', aliases=['h', '?'])
    async def points_help(self, ctx):
        """Shows information about points."""
        embed = DefaultEmbed(ctx)
        embed.title = 'Army Points - Help Page'
        embed.description = f'Army Points are the main currency used by Turtle Bot. They can be used to buy items ' \
                            f'from the shop (`{ctx.prefix}inv shop`)'
        embed.add_field(
            name='How do I get points?',
            value=f'Points can be aquired via a few methods. The first method is by voting for the server. '
                  f'When you vote for the server, you are given 10 points, and a 2x boost to your points for'
                  f' the next six hours. This means, whenever you get points, you get twice as many while the boost '
                  f'lasts.',
            inline=False
        )
        embed.add_field(
            name='Getting Points - Epic Events',
            value='Whenever you spawn an epic event, you get a certain amount of Army Points.\n'
                  'Ultra Bait - 5 points\n'
                  'Epic Seed - 3 points\n'
                  'Coin Trumpet - 1 point.',
            inline=False
        )
        embed.add_field(
            name='Getting Points - Hunting',
            value='Every 100 hunts, you get an amount of Army Points depending on your currently weekly'
                  ' hunt count. If you have less than 500 weekly hunts, you get one point. If you have more than 500, '
                  'but less than 1000 weekly hunts, you get 2 points. If you have 1000 or more weekly hunts, you get'
                  '3 points. This happens every 100 weekly hunts.',
            inline=False
        )

        return await ctx.send(embed=embed)

    @commands.command(name='boosts', aliases=['boost'])
    async def all_boosts(self, ctx):
        """Shows all of your active items and boosts."""
        embed = DefaultEmbed(
            ctx,
            title=f"{ctx.author.name}'s boosts"
        )
        # point boost
        point_data = await self.bot.mdb['point_boost'].find_one({'_id': ctx.author.id})
        if point_data:
            now = pendulum.now(tz=pendulum.UTC)
            prev = pendulum.from_timestamp(point_data.get('end_time'))
            dur = prev - now

            if dur.total_seconds() < 0:
                await self.bot.mdb['point_boost'].delete_one({'_id': ctx.author.id})
            else:
                embed.add_field(
                    name='Point Boost',
                    value=f'Active Point Boost found!\n'
                          f'**Multiplier:** {point_data.get("multiplier")}x\n'
                          f'**Remaining Time:** {dur.in_words()}'
                )
        # epic cd bypass
        cd_data = await self.bot.mdb['epic_cd'].find_one({'_id': ctx.author.id})
        if cd_data:
            embed.add_field(
                name='Epic Epic Slow-mode Bypass',
                value='Active slow-mode bypass found!\n'
                      f'**End Time:** <t:{cd_data.get("end_time")}:R>'
            )
        # extra GA role
        ga_roles = await self.bot.mdb['ga_db'].find({'_id': {'$regex': rf'{ctx.author.id}-(\d+)'}}).to_list(None)
        for item in ga_roles:
            _, role_id = item.get('_id').split('-')
            role_id = int(role_id)
            role = ctx.guild.get_role(role_id)
            embed.add_field(
                name='GA Role - Extra Entries',
                value='GA Role Found!\n'
                      f'**Role:** {role.mention}\n'
                      f'**End Time:** <t:{item.get("end_time")}:R>'
            )

        # special item boost
        special = await self.bot.mdb['special_db'].find({'_id': {'$regex': rf'{ctx.author.id}-(.+)'}}).to_list(None)
        for item in special:
            embed.add_field(
                name='Special Item Boost',
                value=f'Special Item Boost Found!\nThis item grants point milestones every 15 hunts instead of 100.\n'
                      f'**End Time:** <t:{item.get("end_time")}:R>'
            )

        if len(embed.fields) == 0:
            embed.description = 'No boosts found. Buy and activate an item from the shop!'

        return await ctx.send(embed=embed)

    @points.command(name='give')
    @owner_or_mods()
    async def points_admin(self, ctx, who: MemberOrId, amount: int):
        """Give a user an amount of points.
        Not affected by multiplier. Mod+ only."""
        await self.db.update_one(
            {'_id': who.id},
            {'$inc': {'points': amount}},
            upsert=True
        )
        embed = DefaultEmbed(ctx, title='Points Added')
        embed.description = f'{amount} points have been given to {who}'
        embed.add_field(name='New Total', value=f'{await self.get_points(who)} ({amount:+})')

        await self.bot.mdb['log_events'].insert_one(
            {
                'moderator': ctx.author.id,
                'type': 'point_give',
                'recipient': who.id,
                'amount': amount,
                'date': datetime.datetime.now(tz=datetime.timezone.utc)
            }
        )

        await ctx.send(embed=embed)

def setup(bot):
    bot.add_cog(Points(bot))
