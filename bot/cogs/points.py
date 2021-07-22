import logging
import re
import time
import typing

import pendulum
from discord.ext import commands

from utils.constants import EPIC_EVENTS_POINTS, POINTS_EMOJI
from utils.converters import MemberOrId
from utils.embeds import DefaultEmbedMessage, DefaultEmbed
from utils.embeds import MemberEmbed

log = logging.getLogger(__name__)


class Points(commands.Cog):
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

        if weekly % 100 == 0 and weekly != 0:
            # if our current hunt is a multiple of 100
            # add a point depending on the current weekly hunt count
            hunt_point = 1 + (weekly >= 500) + (weekly >= 1000)
            await self.mod_points(msg.author.id, hunt_point)
            await msg.channel.send(embed=DefaultEmbedMessage(self.bot, title='Point Added!',
                                                             description=f'You reached {weekly} weekly hunts, and got '
                                                                         f'{hunt_point} point(s).'))

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
            value=f'{POINTS_EMOJI} {points} army points'
        )

        return await ctx.send(embed=embed)

    @points.command(name='boosts', aliases=['boost', 'b'])
    async def points_boost(self, ctx):
        """Shows your current point boost status."""

        boost_data = await self.bot.mdb['point_boost'].find_one({'_id': ctx.author.id})

        if boost_data:
            now = pendulum.now(tz=pendulum.UTC)
            prev = pendulum.from_timestamp(boost_data.get('end_time'))
            dur = prev - now

            if dur.total_seconds() < 0:
                await self.bot.mdb['point_boost'].delete_one({'_id': ctx.author.id})
            else:
                embed = DefaultEmbed(ctx)
                embed.title = 'Active Point Boost'
                embed.description = "You currently have an active point multiplier for hunting and epic events."
                embed.add_field(name='Multiplier', value=f'{boost_data.get("multiplier")}x')
                embed.add_field(name='Time Remaining', value=dur.in_words())
                embed.add_field(name='How to Vote?', value='Vote for the server by visting '
                                           '[this link](https://top.gg/servers/713541415099170836/vote)')

                return await ctx.send(embed=embed)

        return await ctx.send(embed=DefaultEmbed(ctx, title='No boosts found',
                                                 description='You do not have an active point boost.'
                                                            ' You can get one by voting for the server').add_field(
            name='How to Vote?', value='Vote for the server by visting '
                                       '[this link](https://top.gg/servers/713541415099170836/vote)'
        ))

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


def setup(bot):
    bot.add_cog(Points(bot))
