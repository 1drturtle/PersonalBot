from discord.ext import commands
import typing


class MemberOrId(commands.Converter):
    async def convert(self, ctx, arg):

        try:
            member = commands.MemberConverter().convert(ctx, arg)
        except commands.MemberNotFound:
            if str(arg).isnumeric():
                member = await ctx.guild.fetch_member(arg)
            else:
                member = None

        if member is None:
            raise commands.MemberNotFound(f'Could not find a member with arg `{arg}`')

        return member
