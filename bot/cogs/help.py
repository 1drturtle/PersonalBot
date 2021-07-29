import logging
from typing import Optional, List, Dict

import discord
from discord.ext import commands

from utils.embeds import DefaultEmbed

log = logging.getLogger(__name__)


class HelpEmbed(DefaultEmbed):
    def __init__(self, ctx, **kwargs):
        super().__init__(ctx, **kwargs)
        self.set_footer(
            text='Use tb!help [command] or tb!help [category] for more information',
            icon_url=self.footer.icon_url
        )


class BotView(discord.ui.View):
    def __init__(self, cogs, help_cmd):
        super().__init__(timeout=30)
        self.help_cmd = help_cmd
        for cog in cogs:
            self.add_item(CogButton(label=cog.qualified_name))


class CogButton(discord.ui.Button):

    view: BotView

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.style = discord.ButtonStyle.blurple

    async def callback(self, interaction: discord.Interaction):
        if not self.view:
            return

        ctx = self.view.help_cmd.context

        cog = ctx.bot.cogs[self.label]
        self.view.clear_items()
        self.view.stop()
        await ctx.send_help(cog)


class MyHelp(commands.HelpCommand):
    async def send_bot_help(self, mapping: Dict[Optional[commands.Cog], List[commands.Command]]):
        cogs = []
        embed = HelpEmbed(self.context, title='TurtleBot Help')
        for cog, commands in mapping.items():
            filtered = await self.filter_commands(commands, sort=True)
            if cog is None:
                continue
            if len(filtered) >= 1:
                cogs.append(cog)
                embed.add_field(
                    name=cog.qualified_name,
                    value=cog.description or 'No description.'
                )
        embed.add_field(name='More Info', value='To see more information about a specific category, click it\'s button'
                                                ' below. The buttons will expire after 30 seconds.')
        view = BotView(cogs, self)
        dest = self.get_destination()
        return await dest.send(embed=embed, view=view)

    async def send_cog_help(self, cog):
        embed = HelpEmbed(self.context, title=f'{cog.qualified_name} Category Help')
        filtered = await self.filter_commands(cog.get_commands(), sort=True)
        out = []
        for command in filtered:
            underline = '__'*(isinstance(command, commands.Group))
            out.append(f'{underline}`{self.get_command_signature(command).strip()}`{underline} - '
                       f'{command.short_doc or "No description."}')

        embed.add_field(name='Sub-commands', value='An __underlined__ command has sub-commands. See `tb!help <command>`'
                                                   'for more details.')

        embed.description = '\n'.join(out)

        dest = self.get_destination()

        await dest.send(embed=embed)

    async def send_group_help(self, group):
        embed = HelpEmbed(self.context, title=self.get_command_signature(group))
        embed.description = group.help or 'No help found.'
        out = []
        for command in await self.filter_commands(group.commands, sort=True):
            underline = '__' * (isinstance(command, commands.Group))
            x = f'{underline}`{self.get_command_signature(command).strip()}`{underline} -' \
                f' {command.short_doc or "No description available."}'
            out.append(x)
        embed.add_field(name='Sub-commands', value='\n'.join(out) or "No available subcommands.")

        dest = self.get_destination()
        await dest.send(embed=embed)

    async def send_command_help(self, command):
        dest = self.get_destination()
        if len(await self.filter_commands([command])) == 0:
            return await dest.send(
                embed=HelpEmbed(self.context, title='Forbidden', description='You do not have permissions to view the '
                                                                          'help for this command.')
            )
        embed = HelpEmbed(self.context, title=self.get_command_signature(command))
        embed.description = command.help or 'No help provided.'
        if command.aliases:
            embed.add_field(name='Aliases', value=f', '.join(command.aliases))
        await dest.send(embed=embed)

    async def send_error_message(self, error):
        embed = HelpEmbed(self.context, title='Help Error', description=error)
        channel = self.get_destination()
        await channel.send(embed=embed)


def setup(bot):
    bot.help_command = MyHelp()
