import discord
import datetime
import random
from utils.constants import RPG_ARMY_ICON


class DefaultEmbed(discord.Embed):
    def __init__(self, ctx, **kwargs):
        super(DefaultEmbed, self).__init__(**kwargs)
        self.set_author(name=ctx.author.name, icon_url=ctx.author.avatar_url)
        self.set_footer(text=ctx.bot.user.name, icon_url=ctx.bot.user.avatar_url)
        self.timestamp = datetime.datetime.utcnow()
        self.set_thumbnail(url=RPG_ARMY_ICON)

        self.colour = random.randint(0, 0xffffff)


class SuccessEmbed(DefaultEmbed):
    def __init__(self, ctx, **kwargs):
        super(SuccessEmbed, self).__init__(ctx, **kwargs)
        self.colour = discord.Colour.green()


class ErrorEmbed(DefaultEmbed):
    def __init__(self, ctx, **kwargs):
        super(ErrorEmbed, self).__init__(ctx, **kwargs)
        self.colour = discord.Colour.red()


class MemberEmbed(DefaultEmbed):
    def __init__(self, ctx, who, **kwargs):
        super(MemberEmbed, self).__init__(ctx, **kwargs)
        self.set_author(name=who.name, icon_url=who.avatar_url)
