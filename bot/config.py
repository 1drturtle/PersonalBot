import os


class Config:
    def __init__(self):
        self.PREFIX = os.getenv('DISCORD_BOT_PREFIX', 'tb!')
        self.DEV_ID = int(os.getenv('DEV_ID', '175386962364989440'))
        self.TOKEN = os.getenv('DISCORD_BOT_TOKEN')

        self.MONGO_URL = os.getenv('DISCORD_MONGO_URL')
        self.MONGO_DB = os.getenv('MONGO_DB', 'personalbotdbtest')

        self.REDIS_URL = os.getenv('DISCORD_REDIS_URL', 'redis://redis:6379')
        self.REDIS_PASS = os.getenv('DISCORD_REDIS_PASS', None)

        self.DEFAULT_STATUS = os.getenv('DISCORD_STATUS', f'with the API')

        # Version
        self.VERSION = os.getenv('VERSION', 'testing')

        # Error Reporting
        self.SENTRY_URL = os.getenv('SENTRY_URL', None)
        self.ENVIRONMENT = os.getenv('ENVIRONMENT', 'testing')
        self.GUILD_ID = 713541415099170836 if self.ENVIRONMENT == 'production' else 851549590779330590
