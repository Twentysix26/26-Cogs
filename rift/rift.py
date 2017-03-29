import os
from collections import namedtuple

import discord
from discord.ext import commands
from __main__ import send_cmd_help
from cogs.utils.chat_formatting import escape, pagify
from cogs.utils import checks
from .utils.dataIO import dataIO

# Commission made for ScarletRaven, who decided to make it public
# for everyone to enjoy 👍

OpenRift = namedtuple("Rift", ["author", "source", "destination"])


def closecheck(ctx):
    """Admin / manage channel OR private channel"""
    return ctx.message.channel.is_private or checks.admin_or_permissions(
        manage_channel=True)(ctx)


class Rift:
    """Communicate with other servers/channels!"""

    def __init__(self, bot):
        self.bot = bot
        self.settings = dataIO.load_json("data/rift/settings.json")
        self.open_rifts = {}

    @commands.group(pass_context=True)
    async def rift(self, ctx):
        """Communicate with other channels through Red"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @rift.command(name="notify", pass_context=True)
    @checks.is_owner()
    async def _rift_notify(self, ctx, *, notify: bool=None):
        """Sets whether to notify destinations of opening/closing rifts.

        Note that the rift open notification is always sent to Direct Message
        destinations, regardless of this setting."""
        if notify is None:
            await send_cmd_help(ctx)
        elif notify != self.settings["NOTIFY"]:
            self.settings["NOTIFY"] = notify
            dataIO.save_json("data/rift/settings.json", self.settings)
        await self.bot.say("```notify: {}```".format(self.settings["NOTIFY"]))

    @rift.command(name="open", pass_context=True)
    async def _rift_open(self, ctx, *, channel):
        """Opens a rift to another channel

        <channel> may be any channel or user that the bot is connected to,
        even accross servers."""
        def _check(message):
            try:
                return matches[int(message.content)] or True
            except (IndexError, ValueError):
                return False

        author = ctx.message.author
        author_channel = ctx.message.channel

        matches = list(self._search(ctx, channel, True))
        if not matches:
            return await self.bot.say("No channels or users found.")
        if len(matches) == 1:
            name = matches[0]
        else:
            msg = "Multiple results found.\nChoose a channel:\n" + "\n".join(
                "{0} - {1.name} ({1.server.name})".format(i, channel) for i,
                channel in enumerate(matches))
            for page in pagify(msg):
                await self.bot.say(page)
            choice = await self.bot.wait_for_message(author=author,
                                                     timeout=10,
                                                     check=_check,
                                                     channel=author_channel)
            if choice is None:
                await self.bot.say("Never mind, then.")
                return
            name = matches[int(choice.content)]
        channel = name if isinstance(name, discord.Channel) else \
            await self.bot.start_private_message(name)
        try:
            name = "**{} ({})**".format(name, channel.server)
        except AttributeError:
            name = "**{}**".format(name)

        rift = OpenRift(author=author, source=author_channel,
                        destination=channel)
        if author_channel == channel:
            return await self.bot.say("You cannot open a rift to itself.")
        if channel.id in self.settings["BLACKLIST"]:
            return await self.bot.say("That channel has been blacklisted.")
        if rift in self.open_rifts:
            return await self.bot.say("This rift already exists.")

        self.open_rifts[rift] = {}
        if self.settings["NOTIFY"] or channel.is_private:
            try:
                await self.bot.send_message(channel, "**{}** has opened a "
                                            "rift to here.".format(author))
            except Exception:
                return await self.bot.say("I couldn't open a rift to {}."
                                          .format(name))
        await self.bot.send_message(author_channel, "A rift has been opened "
                                    "to {}! Everything you say will be "
                                    "relayed there.\nResponses will be "
                                    "relayed here.\nType `exit` to quit."
                                    .format(name))

    @rift.command(name="close", pass_context=True)
    @commands.check(closecheck)
    async def _rift_close(self, ctx):
        """Closes all rifts that lead to this channel.

        The rifts' source channels will be notified regardless of the notify
        setting."""
        author = ctx.message.author
        channel = ctx.message.channel
        await self._close_rift(author, channel, True)

    @rift.group(pass_context=True)
    @commands.check(closecheck)
    async def blacklist(self, ctx):
        """Configures the rift blacklist.

        Blacklisted channels cannot have rifts opened to them."""
        owner = ctx.message.author.id == self.bot.settings.owner
        if str(ctx.invoked_subcommand) == "rift blacklist":
            await send_cmd_help(ctx)
            if self.settings["BLACKLIST"]:
                channels = []
                for c in self.settings["BLACKLIST"]:
                    channel = discord.utils.get(self.bot.get_all_channels()
                                                if owner else
                                                ctx.message.server.channels,
                                                id=c)
                    if channel:
                        channels.append(channel)
                    else:
                        if owner:
                            channels.append("Direct Message ({})".format(c))
                if channels:
                    for page in pagify("Blacklist: {}".format(", ".join(
                            channels)), [", "]):
                        await self.bot.say("```{}```".format(page.strip(", ")))

    @blacklist.command(name="add", pass_context=True)
    async def _blacklist_add(self, ctx, *, channel: discord.Channel=None):
        """Add the channel to the blacklist.

        If no channel is provided, the current channel is added."""
        channel = channel if channel else ctx.message.channel
        blacklist = self.settings["BLACKLIST"]
        if channel.id in blacklist:
            return await self.bot.say("This channel is already "
                                      "blacklisted.")
        blacklist.append(channel.id)
        dataIO.save_json("data/rift/settings.json", self.settings)
        author = ctx.message.author
        await self._close_rift(author, channel, False)
        await self.bot.say("{} has been added to the blacklist.".format(
            channel))

    @blacklist.command(name="remove", pass_context=True)
    async def _blacklist_remove(self, ctx, *, channel: discord.Channel=None):
        """Remove the channel from the blacklist.

        If no channel is provided, the current channel is added."""
        channel = channel if channel else ctx.message.channel
        blacklist = self.settings["BLACKLIST"]
        if channel.id not in blacklist:
            return await self.bot.say("This channel is already not "
                                      "blacklisted.")
        blacklist.remove(channel.id)
        dataIO.save_json("data/rift/settings.json", self.settings)
        await self.bot.say("{} has been removed from the blacklist."
                           .format(channel))

    @blacklist.command(name="clear")
    @checks.is_owner()
    async def _blacklist_clear(self):
        """Clear the blacklist."""
        del self.settings["BLACKLIST"][:]
        dataIO.save_json("data/rift/settings.json", self.settings)
        await self.bot.say("Blacklist cleared.")

    @rift.command(name="search", pass_context=True)
    async def _rift_search(self, ctx, searchby=None, *, search=None):
        """Searches through open rifts.

        searchby: author, source, or destination. If this isn't provided, all
        three are searched through.
        search: Search for the specified author/source/destination. If this
        isn't provided, the author or channel of the command is used."""
        if searchby is None:
            searchby = (0, 1, 2)
        else:
            try:
                searchby = (("author", "source", "destination").index(
                    searchby.lower()),)
            except ValueError:
                return await self.bot.say("searchby must be author, source, "
                                          "or destination")
        if search is None:
            search = {ctx.message.author, ctx.message.channel,
                      await self.bot.start_private_message(ctx.message.author)}
        else:
            search = self._search(ctx, search, False)
            for channel in search.copy():
                if isinstance(channel, discord.User):
                    search.add(await self.bot.start_private_message(channel))
        res = set()
        for rift in self.open_rifts:
            for i in searchby:
                if rift[i] in search:
                    res.add(rift)
        if res:
            for page in pagify("\n".join("{}: {} ► {}".format(
                    rift.author, rift.source, rift.destination)
                    for rift in res)):
                await self.bot.say(page)
        else:
            await self.bot.say("No rifts were found.")

    async def _close_rift(self, author, channel, notif):
        noclose = True
        for rift in self.open_rifts.copy():
            if rift.destination == channel:
                del self.open_rifts[rift]
                noclose = False
                await self.bot.say("Rift from **{}** closed.".format(
                    rift.source))
                await self.bot.send_message(rift.source, "**{}** has "
                                            "closed the rift to "
                                            "**{}**.".format(
                                                author, channel))
        if noclose and notif:
            await self.bot.say("No rifts were found that connect to here.")

    def _is_command(self, msg):
        if callable(self.bot.command_prefix):
            prefixes = self.bot.command_prefix(self.bot, msg)
        else:
            prefixes = self.bot.command_prefix
        return msg.content.startswith(tuple(prefixes))

    def _search(self, ctx, search, cross):
        author = ctx.message.author
        thisserver = ctx.message.server
        is_owner = author.id == self.bot.settings.owner
        servers = self.bot.servers if cross or is_owner else (thisserver,)
        matches = set()
        for server in servers:
            autmember = None if is_owner else discord.utils.get(
                server.members, id=author.id)
            if not (autmember or is_owner):
                continue
            botmember = server.me
            matches |= {c for c in server.channels if c.type.name == "text" and
                        (not autmember or
                         c.permissions_for(autmember).read_messages) and
                        c.permissions_for(botmember).read_messages and
                        c.permissions_for(botmember).send_messages and
                        (str(c) == search or c.name == search or c.id ==
                         search or c.mention == search)} | \
                       {m for m in server.members if str(m) == search or
                        m.name == search or m.id == search or server ==
                        thisserver and m.display_name == search or
                        m.mention.replace("!", "") == search.replace("!", "")}
        matches.discard(self.bot.user)
        return matches

    async def on_message(self, message):
        if message.author == self.bot.user:
            return
        sent = {}
        for rift, rec in self.open_rifts.copy().items():
            if rift.source == message.channel and rift.author == \
                    message.author:
                if message.content.lower() == "exit":
                    del self.open_rifts[rift]
                    if self.settings["NOTIFY"]:
                        await self.bot.send_message(rift.destination,
                                                    "**{}** has closed the "
                                                    "rift.".format(
                                                        rift.author))
                    await self.bot.send_message(rift.source, "Rift closed.")
                else:
                    if not self._is_command(message):
                        try:
                            rec[message] = await self.bot.send_message(
                                rift.destination, message.content)
                        except Exception:
                            await self.bot.send_message(rift.source,
                                                        "I couldn't send your "
                                                        "message.")
            elif rift.destination == message.channel:
                tup = (rift.source, rift.destination)
                if tup in sent:
                    rec[message] = sent[tup]
                else:
                    rec[message] = sent[tup] = await self.bot.send_message(
                        rift.source, escape("{}: {}".format(
                            message.author, message.content),
                            mass_mentions=True))

    async def on_message_delete(self, message):
        if message.author == self.bot.user:
            return
        for rift, rec in self.open_rifts.items():
            try:
                await self.bot.delete_message(rec.pop(message))
            except (KeyError, discord.errors.NotFound):
                continue

    async def on_message_edit(self, before, after):
        if before.author == self.bot.user:
            return
        sent = set()
        for rift, rec in self.open_rifts.items():
            if rift.source == before.channel and rift.author == \
                    before.author:
                try:
                    await self.bot.edit_message(rec[after], after.content)
                except KeyError:
                    continue
            elif rift.destination == before.channel:
                tup = (rift.source, rift.destination)
                if tup not in sent:
                    try:
                        await self.bot.edit_message(rec[after], escape(
                            "{}: {}".format(after.author, after.content),
                            mass_mentions=True))
                        sent.add(tup)
                    except KeyError:
                        continue


def _check_folders():
    fol = "data/rift"
    if not os.path.exists(fol):
        print("Creating {} folder...".format(fol))
        os.makedirs(fol)


def _check_files():
    fil = "data/rift/settings.json"
    if not dataIO.is_valid_json(fil):
        print("Creating default {}...".format(fil))
        dataIO.save_json(fil, {"NOTIFY": False, "BLACKLIST": []})


def setup(bot):
    _check_folders()
    _check_files()
    bot.add_cog(Rift(bot))
