from discord.ext import commands
import discord

RPG_ARMY_ICON = 'https://cdn.discordapp.com/icons/713541415099170836/83b34dda4bedd3d37de2ee666ff526c3.webp?size=1024'
MOD_OR_ADMIN = [commands.is_owner(), commands.has_role('Admin'), commands.has_role('Moderator')]


def owner_or_mods():
    async def predicate(ctx):
        if await ctx.bot.is_owner(ctx.author):
            return True
        if not ctx.guild:
            raise commands.NoPrivateMessage
        if discord.utils.find(lambda r: r.name in ['Admin', 'Moderator'], ctx.author.roles):
            return True
        return False

    return commands.check(predicate)


TRACKED_COMMANDS = {
    'hunt together': 1,
    'hunt t': 1,
    'hunt hardmode together': 2,
    'hunt together hardmode': 2,
    'hunt h t': 2,
    'hunt t h': 2,
    'ascended hunt hardmode together': 3,
    'ascended hunt together hardmode': 3,
    'ascended hunt h t': 3,
    'ascended hunt t h': 3,
    'hunt': 10,
    'hunt hardmode': 11,
    'hunt h': 12,
    'ascended hunt hardmode': 13,
    'ascended hunt h': 14
}

EPIC_EVENTS = {
    'ultra bait': {'msg': 'Placing the ultra bait...', 'id': 101},
    'epic seed': {'msg': 'Planting the epic seed...', 'id': 102},
    'coin trumpet': {'msg': 'Summoning the coin rain...', 'id': 103}
}

ROLE_MILESTONES = {
    500: 'hunt 500 weekly',
    1000: 'hunt 1000 weekly'
}

EPIC_EVENTS_CHANNEL_NAME = '🐟╏epic🎺events🪓'
DEV_CHANNEL_NAME = '🔬・dev-testing'

EPIC_EVENTS_POINTS = {
    'ultra bait': 5,
    'epic seed': 3,
    'coin trumpet': 1
}

POINTS_EMOJI = '<:rpg_army_by_mommapie:778443713596620901>'
