import time as t

import discord
from discord.ext import commands
from utils.constants import DEV_CHANNEL_NAME
from utils.embeds import DefaultEmbedMessage
import logging

log = logging.getLogger(__name__)

BOT_PERCENT = 0.02


class BotKiller(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.redis = self.bot.redis_db
        self.db = self.bot.mdb['bot_killer']

    async def run_hunt(self, user: discord.Member):
        now = t.time()
        # get data
        data = await self.db.find_one({'_id': user.id})
        if data is None:
            data = {
                'deltas': [],
                'last_delta': now,
                'hunt_count': 0,
                '_id': user.id
            }
            return await self.db.insert_one(data)

        data['deltas'].append(round(now - data['last_delta'], 2))
        data['last_delta'] = now
        data['hunt_count'] = data.get('hunt_count') + 1

        log.debug(f'running bot check {user}\n{data!r}')
        if data['hunt_count'] % 10 == 0:
            log.debug('eagle eye on')
            await self.run_bot_check(user, data)

        await self.db.update_one(
            {'_id': user.id},
            {'$set': data}
        )

    async def run_bot_check(self, user: discord.Member, data: dict):
        # check last ten averages and see how similar they are to each other.
        last_ten = data.get('deltas')[-10:]
        last_value = last_ten.pop(0)
        percents = []
        amount_within_bot = 0
        for v in last_ten:
            percent = (v - last_value) / last_value

            if abs(percent) <= BOT_PERCENT:
                amount_within_bot += 1

            percents.append(round(percent, 3))
            last_value = v

        if amount_within_bot > 5:
            log.debug('possible bot found, logging')
            serv = self.bot.get_guild(self.bot.config.GUILD_ID)
            ch = discord.utils.find(lambda c: c.name == DEV_CHANNEL_NAME, serv.channels)
            embed = DefaultEmbedMessage(self.bot, title='Possible Bot Detected!',
                                        description='I might have found a bot, or someone who is very quick.'
                                                    ' The rest of these numbers are specialized details.')
            embed.add_field(name='Percent Deltas', value=', '.join([str(x) for x in percents]))
            embed.add_field(name='Amount below threshold', value=amount_within_bot)
            embed.add_field(name='Culprit', value=user.mention, inline=False)

            return await ch.send(embed=embed)


def setup(bot):
    bot.add_cog(BotKiller(bot))
