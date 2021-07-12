import functools
from io import BytesIO

import discord
from PIL import Image, ImageDraw, ImageFont
from discord.ext import commands


def create_profile(ctx, avatar) -> BytesIO:
    img = Image.open('data/raw_pfp.png')
    pfp = Image.open(avatar)
    # processing
    # add profile
    img.paste(
        pfp, (35, 35)
    )
    # add user name
    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype('data/Calibri.ttf', 32)

    draw.text(
        (180, 40),
        text=ctx.author.name,
        font=font
    )

    # ouput
    output = BytesIO()
    img.save(output, 'png')
    output.seek(0)

    return output


class Profile(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.command(name='profile', aliases=['pfp', 'p'], hidden=True)
    @commands.is_owner()
    async def profile(self, ctx):
        """Shows your current profile (WIP)"""

        avatar = BytesIO(await ctx.author.avatar_url_as(size=256).read())
        cmd = functools.partial(create_profile, ctx, avatar)
        profile = await self.bot.loop.run_in_executor(None, func=cmd)

        await ctx.send(
            file=discord.File(
                fp=profile, filename='profile.png'
            )
        )


def setup(bot):
    bot.add_cog(Profile(bot))
