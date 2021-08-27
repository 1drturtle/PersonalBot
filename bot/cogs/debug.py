import logging
from typing import Optional

import discord
from discord.ext import commands

from utils.constants import owner_or_mods
from utils.embeds import DefaultEmbed, ErrorEmbed

log = logging.getLogger(__name__)


class Debug(commands.Cog):
    """Commands to get more information from Discord than is provided."""
    def __init__(self, bot):
        self.bot = bot

    async def cog_check(self, ctx):
        if ctx.author.id == self.bot.dev_id:
            return True
        if not getattr(ctx.guild, 'id', 0) in self.bot.whitelist:
            return False
        if not discord.utils.find(lambda r: r.name.lower() == 'staff', ctx.author.roles):
            return False
        return True

    @commands.command(name='message', aliases=['minfo'])
    async def message_info(self, ctx, ch: Optional[discord.TextChannel], msg_id: int):
        """Shows the information of a message."""
        if not ch:
            ch = ctx.channel

        try:
            msg = await ch.fetch_message(msg_id)
        except (discord.NotFound, discord.Forbidden):
            return await ctx.send(
                embed=ErrorEmbed(ctx, title='Message Not Found', description='Could not find that message.')
            )

        embed = DefaultEmbed(ctx)
        embed.title = 'Message Information'
        embed.add_field(
            name='Message Author', value=f'{msg.author.mention} ({msg.author.id})'
        )
        embed.add_field(
            name='Message Timestamp', value=f'<t:{int(msg.created_at.timestamp())}:T>'
        )
        embed.add_field(name='Message Content', value=f'`{msg.content}`' or 'No content.')

        await ctx.send(embed=embed)

    @commands.command(name='fixlock')
    @commands.has_role(798727974886703165)
    async def fix_locked(self, ctx):
        """Fixes the Epic Event channel lock."""
        ch = ctx.guild.get_channel(740291010483191827)
        overwrites = ch.overwrites
        r = ctx.guild.get_role(734123413731541002)
        perms = overwrites.get(r, discord.PermissionOverwrite())
        perms.update(send_messages=None)
        overwrites.update({r: perms})
        await ch.edit(overwrites=overwrites)
        await ctx.send(embed=DefaultEmbed(
            ctx,
            title='Channel Permissions Fixed',
            description=f'<#{ch.id}> has been unlocked.'
        ))

    @commands.command('blacklist')
    @owner_or_mods()
    async def blacklist_channel(self, ctx, channel: discord.TextChannel):
        """
        Causes TurtleBot to not respond in the specified channel.
        Requires Mod or Higher.
        """

        embed = DefaultEmbed(ctx)
        embed.title = 'Channel Blacklisted'
        embed.description = f'TurtleBot will no longer respond to commands in <#{channel.id}>'

        await self.bot.mdb['channel_blacklist'].update_one(
            {'_id': channel.id},
            {'$set': {
                'user': ctx.author.id,
            }},
            upsert=True
        )

        self.bot.channel_blacklist.add(channel.id)

        await ctx.send(embed=embed)
        log.info(f'[Debug] Channel #{channel.name} ({channel.id}) blacklisted by {ctx.author} ({ctx.author.id}')


def setup(bot):
    bot.add_cog(Debug(bot))
