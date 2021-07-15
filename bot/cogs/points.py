import typing

from discord.ext import commands

from utils.embeds import MemberEmbed
from utils.converters import MemberOrId
from utils.constants import EPIC_EVENTS_POINTS
from utils.embeds import DefaultEmbedMessage, DefaultEmbed
import logging
import re
import time

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
            {'$inc': {'points': amount * multiplier}}
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

        mention = re.match(r'<@(!?)(?P<id>\d+)>', embed.description.lower())
        if not mention:
            return

        member = msg.guild.get_member(mention.group('id'))
        if not member:
            return

        await self.mod_points(member.id, 10)

        new_end = round(time.time()) + 60 * 60 * 6  # 6 hours
        await self.bot.mdb['point_boost'].update_one(
            {'_id': member.id},
            {'$set': {'multiplier': 2, 'end_time': new_end}}
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
            value=f':crossed_swords: {points} army points'
        )

        return await ctx.send(embed=embed)

    @points.command(name='boosts')
    async def points_boost(self, ctx):
        """Shows your current point boost status."""

        boost_data = await self.bot.mdb['point_boost'].find_one({'_id': ctx.author.id})
        if not boost_data:
            return await ctx.send(embed=DefaultEmbed(ctx, title='No boosts found',
                                                     description='You do not have an active point boost.'
                                                                 ' You can get one by voting for the server'))


def setup(bot):
    bot.add_cog(Points(bot))
