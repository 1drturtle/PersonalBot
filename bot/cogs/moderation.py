import typing

import discord
from discord.ext import commands

from utils.embeds import SuccessEmbed, ErrorEmbed


def role_or_permissions(role_name, **perms):
    original = commands.has_permissions(**perms).predicate

    async def extended_check(ctx):
        if ctx.guild is None:
            return False
        if ctx.guild.owner_id == ctx.author.id:
            return True
        if discord.utils.find(lambda r: r.name == role_name, ctx.author.roles):
            return True
        return await original(ctx)

    return commands.check(extended_check)


async def member_or_snowflake(ctx, arg) -> typing.Union[discord.Member, discord.Object]:
    converter = commands.MemberConverter()
    try:
        member = await converter.convert(ctx, arg)
    except commands.MemberNotFound:
        if arg.isnumeric():
            member = discord.Object(int(arg))
        else:
            raise
    return member


NO_REASON = 'No reason provided.'


class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='kick')
    @role_or_permissions('Staff', kick_members=True)
    async def kick(self, ctx, user: str, *, reason: typing.Optional[str]):
        """Kicks a member from the server. You must have kick members permission, or the Staff role."""
        try:
            member = await member_or_snowflake(ctx, user)
        except commands.MemberNotFound:
            embed = ErrorEmbed(ctx, title='Kick Error', description=f'Could not find user by name or id of `{user}`')
            return await ctx.send(embed=embed)
        if isinstance(member, discord.Object):
            embed = ErrorEmbed(ctx)
            embed.title = 'Kick Error'
            embed.description = 'You cannot kick a user who is not in the server.'

            return await ctx.send(embed=embed)

        if member.top_role >= ctx.author.top_role or member.top_role >= ctx.guild.me.top_role:
            if ctx.guild.owner_id != ctx.author.id:
                embed = ErrorEmbed(ctx)
                embed.title = f'Kick Error'
                embed.description = 'You cannot kick someone who has the same role or higher than you or the bot.'

                return await ctx.send(embed=embed)

        try:
            await ctx.guild.kick(member, reason=f'Kicked by {ctx.author.name}. Reason: {reason or NO_REASON}')
        except discord.Forbidden:
            embed = ErrorEmbed(ctx)
            embed.title = 'Kick Error'
            embed.description = 'I do not have permissions to kick this user. Make sure that my role is above theirs,' \
                                ' and that I have kick permissions.'

            return await ctx.send(embed=embed)

        embed = SuccessEmbed(ctx)
        embed.title = 'Member Kicked'
        embed.description = f'<@{member.id}> has been kicked by {ctx.author.mention}.\nReason: {reason or NO_REASON}'

        return await ctx.send(embed=embed)

    @commands.command(name='ban')
    @role_or_permissions('Admin', ban_members=True)
    async def ban(self, ctx, user: str, *, reason: typing.Optional[str]):
        """Bans a member from the server. You must have Ban Members permission, or the Admin role."""
        try:
            member = await member_or_snowflake(ctx, user)
        except commands.MemberNotFound:
            embed = ErrorEmbed(ctx, title='Ban Error', description=f'Could not find user by name or id of `{user}`')
            return await ctx.send(embed=embed)
        if isinstance(member, discord.Object):
            pass
        elif member.top_role >= ctx.author.top_role or member.top_role >= ctx.guild.me.top_role:
            if ctx.guild.owner_id != ctx.author.id:
                embed = ErrorEmbed(ctx)
                embed.title = f'Ban Error'
                embed.description = 'You cannot ban someone who has the same role or higher than you.'
                return await ctx.send(embed=embed)

        try:
            await ctx.guild.ban(member, reason=f'Banned by {ctx.author.name}. Reason: {reason or NO_REASON}')
        except discord.Forbidden:
            embed = ErrorEmbed(ctx)
            embed.title = 'Ban Error'
            embed.description = 'I do not have permissions to ban this user. Make sure that my role is above theirs,' \
                                ' and that I have ban permissions.'

            return await ctx.send(embed=embed)

        embed = SuccessEmbed(ctx)
        embed.title = 'Member Banned'
        embed.description = f'<@{member.id}> has been banned by {ctx.author.mention}.\nReason: {reason or NO_REASON}'

        return await ctx.send(embed=embed)

    @commands.command(name='unban')
    @role_or_permissions('Admin', ban_members=True)
    async def unban(self, ctx, user: discord.User, *, reason: typing.Optional[str]):
        """Un-bans a user from the server. Requires ban members permissions, or the Admin role."""

        try:
            await ctx.guild.unban(user, reason=f'Un-banned by {ctx.author.name}. Reason: {reason or NO_REASON}')
        except discord.Forbidden:
            embed = ErrorEmbed(ctx, title='Unban Error.', description='I do not have permissions to unban this user.'
                                                                      ' Ensure that I have the `Ban Member`'
                                                                      'permission to be able to do this action.')

        except discord.HTTPException:
            embed = ErrorEmbed(ctx, title='Unban Error', description='An error occurred while trying to unban this '
                                                                     'user. Make sure they are the correct person '
                                                                     'you are trying to un-ban.')

        else:
            embed = SuccessEmbed(ctx, title='User Unbanned', description=f'{user.name}#{user.discriminator} has'
                                                                         f'been unbanned from the server by '
                                                                         f'{ctx.author.name}.'
                                                                         f'\nReason: {reason or NO_REASON}')

        return await ctx.send(embed=embed)


def setup(bot):
    bot.add_cog(Moderation(bot))
