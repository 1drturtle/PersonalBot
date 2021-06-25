import asyncio
import logging
import sys

import aioredis
import discord
import motor.motor_asyncio
import pendulum
from discord.ext import commands

from config import Config

config = Config()


async def get_prefix(client, message):
    if not message.guild:
        return commands.when_mentioned_or(config.PREFIX)(client, message)
    guild_id = str(message.guild.id)
    if guild_id in client.prefixes:
        prefix = client.prefixes.get(guild_id, config.PREFIX)
    else:
        dbsearch = await client.mdb['prefixes'].find_one({'guild_id': guild_id})
        if dbsearch is not None:
            prefix = dbsearch.get('prefix', config.PREFIX)
        else:
            prefix = config.PREFIX
        client.prefixes[guild_id] = prefix
    return commands.when_mentioned_or(prefix)(client, message)


class MyBot(commands.Bot):
    def __init__(self, command_prefix=get_prefix, desc: str = '', **options):
        self.launch_time = pendulum.now(tz=pendulum.tz.UTC)
        self.loop = asyncio.get_event_loop()

        self.config = config

        self.mongo_client = motor.motor_asyncio.AsyncIOMotorClient(config.MONGO_URL)
        self.mdb = self.mongo_client[config.MONGO_DB]

        self.redis_db: aioredis.ConnectionsPool = self.loop.run_until_complete(
            aioredis.create_redis_pool('redis://redis:6379')
        )

        self.default_prefix = config.PREFIX
        self.prefixes = dict()

        self.environment = config.ENVIRONMENT
        self.dev_id = config.DEV_ID

        self.whitelist = set()

        self.loop.run_until_complete(
            self.startup()
        )

        super(MyBot, self).__init__(command_prefix, description=desc, **options)

    @property
    def uptime(self):
        return pendulum.now(tz=pendulum.tz.UTC) - self.launch_time

    async def startup(self):
        data = await self.mdb['whitelist'].find().to_list(length=None)

        self.whitelist = set([d.get('_id') for d in data])

    async def close(self):
        self.redis_db.close()
        await self.redis_db.wait_closed()
        await super().close()


log_formatter = logging.Formatter('%(levelname)s | %(name)s: %(message)s')
handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(log_formatter)
logger = logging.getLogger()
logger.setLevel(logging.DEBUG if config.ENVIRONMENT == 'testing' else logging.INFO)
logger.addHandler(handler)
log = logging.getLogger('main')

# Make discord logs a bit quieter
logging.getLogger('discord.gateway').setLevel(logging.WARNING)
logging.getLogger('discord.client').setLevel(logging.ERROR)
logging.getLogger('discord.http').setLevel(logging.INFO)
logging.getLogger('discord.state').setLevel(logging.INFO)

# Other logs
logging.getLogger('asyncio').setLevel(logging.WARNING)

intents = discord.Intents(guilds=True, members=False, messages=True)

description = 'Personal Bot developed by Dr Turtle#1771'

bot = MyBot(desc=description, intents=intents, allowed_mentions=discord.AllowedMentions.none(),
            case_insensitive=True)


@bot.event
async def on_ready():

    bot.ready_time = pendulum.now(tz=pendulum.tz.UTC)
    log.info(
        '\n' + (f'-'*20) + '\n'
        f'- {bot.user.name} Ready -\n'
        f'- Prefix: {bot.default_prefix} | Servers: {len(bot.guilds)} \n' +
        (f'-'*20)
    )


COGS = {'jishaku', 'cogs.error_handler', 'cogs.info', 'cogs.tracker', 'cogs.leaderboard'}

for cog in COGS:
    try:
        bot.load_extension(cog)
    except Exception as e:
        raise e
        # log.error(f'Error loading cog {cog}: {str(e)}')

if __name__ == '__main__':
    bot.run(config.TOKEN)
