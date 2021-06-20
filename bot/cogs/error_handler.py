import discord
import traceback
import sys
from discord.ext import commands

from utils.embeds import ErrorEmbed
import pendulum

# taken, modified from https://gist.githubusercontent.com/EvieePy/7822af90858ef65012ea500bcecf1612/raw
# /ef9c09938d4cc094482d4b145fa2c1a78b650d8f/error_handler.py


class CommandErrorHandler(commands.Cog):

    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        """The event triggered when an error is raised while invoking a command.

        Parameters
        ------------
        ctx: commands.Context
            The context used for command invocation.
        error: commands.CommandError
            The Exception raised.
        """

        if ctx.command:
            cmd_name = f'`{ctx.prefix}{ctx.command.qualified_name}`'
        else:
            cmd_name = 'This command'

        # This prevents any commands with local handlers being handled here in on_command_error.
        if hasattr(ctx.command, 'on_error'):
            return

        # This prevents any cogs with an overwritten cog_command_error being handled here.
        cog = ctx.cog
        if cog:
            if cog._get_overridden_method(cog.cog_command_error) is not None:
                return

        ignored = (commands.CommandNotFound, )

        # Allows us to check for original exceptions raised and sent to CommandInvokeError.
        # If nothing is found. We keep the exception passed to on_command_error.
        error = getattr(error, 'original', error)

        # Anything in ignored will return and prevent anything happening.
        if isinstance(error, ignored):
            return

        if isinstance(error, commands.DisabledCommand):
            await ctx.send(
                embed=ErrorEmbed(ctx, title='Disabled Command', description=f'`{cmd_name}` has been disabled until'
                                                                            f'further notice.')
            )

        elif isinstance(error, commands.NoPrivateMessage):
            try:
                await ctx.author.send(
                    embed=ErrorEmbed(ctx, title='No DM\'s', description=f'`{cmd_name}` cannot be used in private'
                                                                        f'messages.')
                )
            except discord.HTTPException:
                pass

        elif isinstance(error, commands.CommandOnCooldown):
            remaining = pendulum.duration(seconds=error.retry_after)
            await ctx.send(
                embed=ErrorEmbed(ctx, title='Command on Cooldown!', description=f'`{cmd_name}` is on cooldown for'
                                                                                f' {remaining.in_words()}.')
            )

        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(
                embed=ErrorEmbed(ctx, title='Missing Required Argument',
                                 description=f'Missing required argument `{error.param.name}` for `{cmd_name}`')
            )

        elif isinstance(error, commands.BadArgument):
            await ctx.send(
                embed=ErrorEmbed(ctx,
                                 title='Invalid Argument',
                                 description=f'`{cmd_name} was passed an invalid argument. ')
            )

        elif isinstance(error, discord.Forbidden):
            err = ErrorEmbed(ctx,
                             title='Forbidden',
                             description=f'I do not have permissions to perform the actions necessary to run'
                                         f' `{cmd_name}`.')
            try:
                await ctx.send(embed=err)
            except discord.Forbidden:
                try:
                    await ctx.author.send(embed=err)
                except discord.Forbidden:
                    pass
                except discord.HTTPException:
                    pass

        elif isinstance(error, commands.CheckFailure):
            pass

        elif isinstance(error, commands.MemberNotFound):
            await ctx.send(embed=ErrorEmbed(ctx,
                                            title='Member Not Found',
                                            description='Could not find the member based on the provided arguments.'))

        else:
            # All other Errors not returned come here. And we can just print the default TraceBack.
            print('Ignoring exception in command {}:'.format(ctx.command), file=sys.stderr)
            traceback.print_exception(type(error), error, error.__traceback__, file=sys.stderr)


def setup(bot):
    bot.add_cog(CommandErrorHandler(bot))
