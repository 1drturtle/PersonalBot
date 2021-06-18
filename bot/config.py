import os


class Config:
    def __init__(self):
        self.PREFIX = os.getenv('DISCORD_BOT_PREFIX', '=')
        self.DEV_ID = int(os.getenv('DEV_ID', '175386962364989440'))
        self.TOKEN = os.getenv('DISCORD_BOT_TOKEN')
        self.MONGO_URL = os.getenv('DISCORD_MONGO_URL')
        self.MONGO_DB = os.getenv('MONGO_DB', 'personalbotdbtest')
        self.DEFAULT_STATUS = os.getenv('DISCORD_STATUS', f'with the API')

        # Version
        self.VERSION = os.getenv('VERSION', 'testing')

        # Error Reporting
        self.SENTRY_URL = os.getenv('SENTRY_URL', None)
        self.ENVIRONMENT = os.getenv('ENVIRONMENT', 'testing')
