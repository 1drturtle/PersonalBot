import time as t

import discord
from discord.ext import commands
from utils.constants import DEV_CHANNEL_NAME, MOD_OR_ADMIN
from utils.converters import MemberOrId
from utils.embeds import DefaultEmbedMessage, SuccessEmbed, ErrorEmbed, DefaultEmbed
import logging

log = logging.getLogger(__name__)

BOT_PERCENT = 0.015


class BotKiller(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.redis = self.bot.redis_db
        self.db = self.bot.mdb['bot_killer']

    async def run_hunt(self, msg: discord.Message):
        user = msg.author
        now = t.time()
        # get data
        data = await self.db.find_one({'_id': user.id})
        if data is None:
            data = {
                'deltas': [],
                'last_delta': now,
                'hunt_count': 0,
                'alert_count': 0,
                '_id': user.id
            }
            return await self.db.insert_one(data)

        if data.get('whitelist', False):
            return

        data['deltas'].append(round(now - data['last_delta'], 2))
        data['last_delta'] = now
        data['hunt_count'] = data.get('hunt_count') + 1

        log.debug(f'running bot check {user}\n{data!r}')
        if data['hunt_count'] % 10 == 0:
            log.debug('eagle eye on')
            await self.run_bot_check(msg, data)

        await self.db.update_one(
            {'_id': user.id},
            {'$set': data}
        )

    async def run_bot_check(self, msg: discord.Message, data: dict):
        user = msg.author

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

        if amount_within_bot > 7:
            log.debug('possible bot found, logging')

            previous = await self.bot.mdb['bot_killer_events'].find({'uid': user.id}).to_list(None)

            serv = self.bot.get_guild(self.bot.config.GUILD_ID)
            ch = discord.utils.find(lambda c: c.name == DEV_CHANNEL_NAME, serv.channels)
            embed = DefaultEmbedMessage(self.bot, title='Possible Bot Detected!',
                                        description='I might have found a bot, or someone who is very quick.'
                                                    ' The rest of these numbers are specialized details.')
            embed.add_field(name='Percent Deltas', value=', '.join([str(x) for x in percents]))
            embed.add_field(name='Amount below threshold', value=amount_within_bot)
            embed.add_field(name='Time Elapsed Between Hunts', value=', '.join([str(x) for x in last_ten]))
            if data.get('flag', False):
                embed.add_field(name='User Flagged!',
                                value='User has been flagged for suspicious activity in the past.')
            if previous:
                embed.add_field(name='Previous Events', value=f'User has had {len(previous)} previous event(s)')
            embed.add_field(name='Culprit', value=f'{user.mention} ({user.id})', inline=False)
            embed.add_field(name='Last Message Link', value=f'[Message Link (click to jump)]({msg.jump_url})')

            # log event to db
            await self.bot.mdb['bot_killer_events'].insert_one(
                {
                    'uid': user.id,
                    'amount_below': amount_within_bot,
                    'thresholds': percents,
                    'deltas': last_ten
                }
            )

            return await ch.send(embed=embed)

    @commands.group(name='bk', hidden=True, invoke_without_command=True)
    @commands.check_any(*MOD_OR_ADMIN)
    async def killer(self, ctx):
        """Base command for bot-killer functions."""

        return await ctx.send_help(self.killer)

    @killer.group(name='whitelist', aliases=['wl'])
    @commands.check_any(*MOD_OR_ADMIN)
    async def killer_whitelist(self, ctx, who: MemberOrId):
        """Whitelist a user from bot-killer functions."""
        await self.db.update_one({"_id": who.id}, {"$set": {"whitelist": True}})
        return await ctx.send(
            embed=SuccessEmbed(
                ctx,
                title='User Whitelisted',
                description=f'`{who.name}#{who.discriminator}` has been added to the bot-killer whitelist.'
            )
        )

    @killer.command(name='flag')
    @commands.check_any(*MOD_OR_ADMIN)
    async def killer_flag(self, ctx, who: MemberOrId):
        """Flag a user as suspicious in the database."""
        await self.db.update_one({"_id": who.id}, {"$set": {"flag": True}})
        return await ctx.send(
            embed=SuccessEmbed(
                ctx,
                title='User Flagged',
                description=f'`{who.name}#{who.discriminator}` has been added to the bot-killer flag list.'
            )
        )


def setup(bot):
    bot.add_cog(BotKiller(bot))
