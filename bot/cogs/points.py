import typing

from discord.ext import commands

from utils.embeds import MemberEmbed
from utils.converters import MemberOrId
from utils.constants import EPIC_EVENTS_POINTS
from utils.embeds import DefaultEmbedMessage
import logging
import re

log = logging.getLogger(__name__)


class Points(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = self.bot.mdb['points']

    async def cog_check(self, ctx):
        return getattr(ctx.guild, 'id', 0) in self.bot.whitelist

    async def epic_hook(self, author, guild, event_type: str):

        if guild.id not in self.bot.whitelist:
            return

        await self.db.update_one(
            {'_id': author.id},
            {'$inc': {'points': EPIC_EVENTS_POINTS[event_type]}},
            upsert=True
        )

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
            await self.db.update_one({'_id': msg.author.id}, {'$inc': {'points': hunt_point}})
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

        member = msg.guild.get_member(mention.get('id'))
        if not member:
            return

        await self.db.update_one({'_id': msg.author.id}, {'$inc': {'points': 10}})

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
            value=f':crossed_swords: {points} army points'
        )

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Points(bot))
