from discord.ext import commands
import typing


# class MemberOrId(commands.Converter):
#     async def convert(self, ctx, arg):
#
#         try:
#             member = commands.MemberConverter().convert(ctx, arg)
#
#
#         member = await ctx.guild.fetch_member()