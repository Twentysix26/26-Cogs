import discord
import datetime
import os
import asyncio
import re
from discord.ext import commands
from __main__ import send_cmd_help, user_allowed
from cogs.utils import checks
from cogs.utils.dataIO import dataIO
from cogs.utils.chat_formatting import box, pagify, escape_mass_mentions
from random import choice
from copy import deepcopy
from cogs.utils.settings import Settings

__author__ = "Twentysix"

settings = Settings()

class TriggerError(Exception):
    pass

class Unauthorized(TriggerError):
    pass

class NotFound(TriggerError):
    pass

class AlreadyExists(TriggerError):
    pass

class InvalidSettings(TriggerError):
    pass

class Trigger:
    """Custom triggers"""

    def __init__(self, bot):
        self.bot = bot
        self.triggers = []
        self.load_triggers()
        self.stats_task = bot.loop.create_task(self.save_stats())

    @commands.group(pass_context=True)
    async def trigger(self, ctx):
        """Trigger creation commands"""
        if ctx.invoked_subcommand is None:
            await send_cmd_help(ctx)

    @trigger.command(pass_context=True)
    @checks.admin_or_permissions(administrator=True)
    async def create(self, ctx, trigger_name : str, *, triggered_by : str):
        """Creates a trigger"""
        try:
            self.create_trigger(trigger_name, triggered_by, ctx)
        except AlreadyExists:
            await self.bot.say("A trigger with that name already exists.")
        else:
            self.save_triggers()
            await self.bot.say("Trigger created. Entering interactive "
                               "add mode...".format(ctx.prefix))
            trigger = self.get_trigger_by_name(trigger_name)
            wait = await self.interactive_add_mode(trigger, ctx)
            self.save_triggers()

    @trigger.command(pass_context=True)
    @checks.admin_or_permissions(administrator=True)
    async def delete(self, ctx, trigger_name : str):
        """Deletes a trigger"""
        try:
            self.delete_trigger(trigger_name, ctx)
        except Unauthorized:
            await self.bot.say("You're not authorized to delete that trigger.")
        except NotFound:
            await self.bot.say("That trigger doesn't exist.")
        else:
            await self.bot.say("Trigger deleted.")

    @trigger.command(pass_context=True)
    @checks.admin_or_permissions(administrator=True)
    async def add(self, ctx, trigger_name : str, *, response : str=None):
        """Adds a response to a trigger

        Leaving the response argument empty will enable interactive mode

        Owner only:
        Adding a response as 'file: filename.jpg' will send that file as
        response if present in data/trigger/files"""
        author = ctx.message.author
        trigger = self.get_trigger_by_name(trigger_name)

        if trigger is None:
            await self.bot.say("That trigger doesn't exist.")
            return
        if not trigger.can_edit(author):
            await self.bot.say("You're not allowed to edit that trigger.")
            return

        if response is not None:
            trigger.responses.append(response)
            await self.bot.say("Response added.")
        else: # Interactive mode
            await self.interactive_add_mode(trigger, ctx)
        self.save_triggers()

    @trigger.command(pass_context=True)
    @checks.admin_or_permissions(administrator=True)
    async def remove(self, ctx, trigger_name : str):
        """Lets you choose a response to remove"""
        author = ctx.message.author
        trigger = self.get_trigger_by_name(trigger_name)

        if trigger is None:
            await self.bot.say("That trigger doesn't exist.")
            return
        if trigger.responses == []:
            await self.bot.say("That trigger has no responses to delete.")
            return
        if not trigger.can_edit(author):
            await self.bot.say("You're not allowed to do that.")
            return

        msg = None
        current_list = None
        past_messages = []
        quit_msg = "\nType 'exit' to quit removal mode."

        while self.get_n_trigger_responses(trigger) is not None:
            r_list = self.get_n_trigger_responses(trigger, truncate=100)
            if current_list is None:
                current_list = await self.bot.say(r_list + quit_msg)
            else:
                if r_list != current_list.content:
                    await self.bot.edit_message(current_list, r_list + quit_msg)
            msg = await self.bot.wait_for_message(author=author, timeout=15)
            if msg is None:
                await self.bot.say("Nothing else to remove I guess.")
                break
            elif msg.content.lower().strip() == "exit":
                past_messages.append(msg)
                await self.bot.say("Removal mode quit.")
                break
            try:
                i = int(msg.content)
                del trigger.responses[i]
            except:
                pass
            past_messages.append(msg)

        if not trigger.responses:
            await self.bot.say("No more responses to delete.")

        past_messages.append(current_list)
        await self.attempt_cleanup(past_messages)

    async def attempt_cleanup(self, messages):
        try:
            if len(messages) > 1:
                await self.bot.delete_messages(messages)
            else:
                await self.bot.delete_message(messages[0])
        except:
            pass

    @trigger.command(pass_context=True)
    async def info(self, ctx, trigger_name : str):
        """Shows a trigger's info"""
        trigger = self.get_trigger_by_name(trigger_name)
        if trigger:
            msg = "Name: {}\n".format(trigger.name)
            owner_name = discord.utils.get(self.bot.get_all_members(), id=trigger.owner)
            owner_name = owner_name if owner_name is not None else "not found"
            msg += "Owner: {} ({})\n".format(owner_name, trigger.owner)
            trigger_type = "all responses" if trigger.type == "all" else "random response"
            msg += "Type: {}\n".format(trigger_type)
            influence = "server" if trigger.server is not None else "global"
            msg += "Influence: {}\n".format(influence)
            cs = "yes" if trigger.case_sensitive else "no"
            msg += "Case Sensitive: {}\n".format(cs)
            regex = "yes" if trigger.regex else "no"
            msg += "Regex: {}\n".format(regex)
            msg += "Cooldown: {} seconds\n".format(trigger.cooldown)
            msg += "Triggered By: \"{}\"\n".format(trigger.triggered_by.replace("`", "\\`"))
            msg += "Payload: {} responses\n".format(len(trigger.responses))
            msg += "Triggered: {} times\n".format(trigger.triggered)
            await self.bot.say(box(msg, lang="xl"))
        else:
            await self.bot.say("There is no trigger with that name.")

    @trigger.command(pass_context=True)
    async def show(self, ctx, trigger_name : str):
        """Shows all responses of a trigger"""
        trigger = self.get_trigger_by_name(trigger_name)
        if trigger:
            payload = self.elaborate_payload(trigger.responses, truncate=9999)
            if payload:
                payload = "\n\n".join(payload)
                if len(payload) > 2000:
                    for page in pagify(payload, delims=[" "]):
                        await self.bot.whisper(page)
                else:
                    await self.bot.say(payload)
            else:
                await self.bot.say("That trigger has no responses.")
        else:
            await self.bot.say("That trigger doesn't exist.")

    @trigger.command(name="list", pass_context=True)
    async def _list(self, ctx, trigger_type="local"):
        """Lists local / global triggers

        Defaults to local"""
        server = ctx.message.server
        results = []
        if trigger_type == "local":
            for trigger in self.triggers:
                if trigger.server == server.id:
                    results.append(trigger)
        elif trigger_type == "global":
            for trigger in self.triggers:
                if trigger.server is None:
                    results.append(trigger)
        else:
            await self.bot.say("Invalid type.")
            return
        if results:
            results = ", ".join([r.name for r in results])
            await self.bot.say("```\n{}\n```".format(results))
        else:
            await self.bot.say("I couldn't find any trigger of that type.")


    @trigger.command(name="set", pass_context=True)
    @checks.admin_or_permissions(administrator=True)
    async def _set(self, ctx, trigger_name : str, setting : str, *,
                   value : str=None):
        """Edits the settings of each trigger

        Settings:

        cooldown <seconds>
        phrase <word(s) that triggers it>
        response <all or random>
        casesensitive
        regex

        Owner only:
        influence <global or local>

        Response set to 'all' outputs all responses
        Response set to 'random' outputs one at random"""
        try:
            self.change_trigger_settings(ctx, trigger_name, setting, value)
        except NotFound:
            await self.bot.say("That trigger doesn't exist.")
        except Unauthorized:
            await self.bot.say("You're not authorized to edit that triggers' "
                               "settings.")
        except InvalidSettings:
            await self.bot.say("Invalid settings.")
        except:
            await self.bot.say("Invalid settings.")
        else:
            self.save_triggers()
            await self.bot.say("Trigger successfully modified.")

    @trigger.command(pass_context=True)
    async def search(self, ctx, *, search_terms : str):
        """Returns triggers matching the search terms"""
        result = self.search_triggers(search_terms.lower())
        if result:
            result = ", ".join(sorted([t.name for t in result]))
            await self.bot.say("Triggers found:\n\n{}".format(result))
        else:
            await self.bot.say("No triggers matching your search.")

    def get_trigger_by_name(self, name):
        for trigger in self.triggers:
            if trigger.name.lower() == name.lower():
                return trigger
        return None

    def search_triggers(self, search_terms):
        results = []
        for trigger in self.triggers:
            if search_terms in trigger.name.lower():
                results.append(trigger)
                continue
            for payload in trigger.responses:
                if search_terms in payload.lower():
                    results.append(trigger)
                    break
            else:
                if search_terms in trigger.triggered_by.lower():
                    results.append(trigger)
        return results

    def create_trigger(self, name, triggered_by, ctx):
        trigger = self.get_trigger_by_name(name)
        if not trigger:
            author = ctx.message.author
            trigger = TriggerObj(name=name,
                                 triggered_by=triggered_by,
                                 owner=author.id,
                                 server=author.server.id
                                )
            self.triggers.append(trigger)
        else:
            raise AlreadyExists()

    def delete_trigger(self, name, ctx):
        trigger = self.get_trigger_by_name(name)
        if trigger:
            if not trigger.can_edit(ctx.message.author):
                raise Unauthorized()
            self.triggers.remove(trigger)
            self.save_triggers()
        else:
            raise NotFound()

    def elaborate_payload(self, payload, truncate=50, escape=True):
        shortened = []
        for p in payload:
            if escape:
                p = (p.replace("`", "\\`")
                      .replace("*", "\\*")
                      .replace("_", "\\_")
                      .replace("~", "\\~"))
                p = escape_mass_mentions(p)
            if len(p) < truncate:
                shortened.append(p)
            else:
                shortened.append(p[:truncate] + "...")
        return shortened

    def change_trigger_settings(self, ctx, trigger_name, setting, value):
        author = ctx.message.author
        server = author.server
        trigger = self.get_trigger_by_name(trigger_name)
        setting = setting.lower()
        if trigger is None:
            raise NotFound()
        if not trigger.can_edit(author):
            raise Unauthorized
        if setting == "response":
            value = value.lower()
            if value in ("all", "random"):
                trigger.type = value
            else:
                raise InvalidSettings()
        elif setting == "cooldown":
            value = int(value)
            if not value < 1:
                trigger.cooldown = value
            else:
                raise InvalidSettings()
        elif setting == "influence":
            value = value.lower()
            if author.id != settings.owner:
                raise Unauthorized()
            if value in ("local", "global"):
                if value == "local":
                    trigger.server = server.id
                else:
                    trigger.server = None
            else:
                raise InvalidSettings()
        elif setting == "phrase":
            assert value is not None
            value = str(value)
            if len(value) > 0:
                trigger.triggered_by = value
            else:
                raise InvalidSettings()
        elif setting == "casesensitive":
            trigger.case_sensitive = not trigger.case_sensitive
        elif setting == "regex":
            trigger.regex = not trigger.regex
        else:
            raise InvalidSettings()

    async def interactive_add_mode(self, trigger, ctx):
        author = ctx.message.author
        msg = ""
        await self.bot.say("Everything you type will be added as response "
                               "to the trigger. Type 'exit' to quit.")
        while msg is not None:
            msg = await self.bot.wait_for_message(author=author, timeout=60)
            if msg is None:
                await self.bot.say("No more responses then. "
                                   "Your changes have been saved.")
                break
            if msg.content.lower().strip() == "exit":
                await self.bot.say("Your changes have been saved.")
                break
            trigger.responses.append(msg.content)

    def get_n_trigger_responses(self, trigger, *, truncate=2000):
        msg = ""
        responses = trigger.responses
        i = 0
        for r in responses:
            if len(r) > truncate:
                r = r[:truncate] + "..."
            r = r.replace("`", "\\`").replace("*", "\\*").replace("_", "\\_")
            msg += "{}. {}\n".format(i, r)
            i += 1
        if msg != "":
            return box(msg, lang="py")
        else:
            return None

    def is_command(self, msg):
        for p in self.bot.command_prefix:
            if msg.startswith(p):
                return True
        return False

    def elaborate_response(self, trigger, r):
        if trigger.owner != settings.owner:
            return "text", r
        if not r.startswith("file:"):
            return "text", r
        else:
            path = r.replace("file:", "").strip()
        path = os.path.join("data", "trigger", "files", path)
        print(path)
        if os.path.isfile(path):
            return "file", path
        else:
            return "text", r

    async def on_message(self, message):
        channel = message.channel
        author = message.author

        if message.server is None:
            return

        if author == self.bot.user:
            return

        if not user_allowed(message):
            return

        if self.is_command(message.content):
            return

        for trigger in self.triggers:
            if not trigger.check(message):
                continue
            payload = trigger.payload()
            for p in payload:
                resp_type, resp = self.elaborate_response(trigger, p)
                if resp_type == "text":
                    await self.bot.send_message(channel, resp)
                elif resp_type == "file":
                    await self.bot.send_file(channel, resp)

    async def save_stats(self):
        """Saves triggers every 10 minutes to preserve stats"""
        await self.bot.wait_until_ready()
        try:
            await asyncio.sleep(60)
            while True:
                self.save_triggers()
                await asyncio.sleep(60 * 10)
        except asyncio.CancelledError:
            pass

    def load_triggers(self):
        triggers = dataIO.load_json("data/trigger/triggers.json")
        for trigger in triggers:
            self.triggers.append(TriggerObj(**trigger))

    def save_triggers(self):
        triggers = [t.export() for t in self.triggers]
        dataIO.save_json("data/trigger/triggers.json", triggers)

    def __unload(self):
        self.stats_task.cancel()
        self.save_triggers()

class TriggerObj:
    def __init__(self, **kwargs):
        self.name = kwargs.get("name")
        self.owner = kwargs.get("owner")
        self.triggered_by = kwargs.get("triggered_by")
        self.responses = kwargs.get("responses", [])
        self.server = kwargs.get("server") # if it's None, the trigger will be implicitly global
        self.type = kwargs.get("type", "all") # Type of payload. Types: all, random
        self.case_sensitive = kwargs.get("case_sensitive", False)
        self.regex = kwargs.get("regex", False)
        self.cooldown = kwargs.get("cooldown", 1) # Seconds
        self.triggered = kwargs.get("triggered", 0) # Counter
        self.last_triggered = datetime.datetime(1970, 2, 6) # Initialized

    def export(self):
        data = deepcopy(self.__dict__)
        del data["last_triggered"]
        return data

    def check(self, msg):
        content = msg.content
        triggered_by = self.triggered_by
        if (self.server == msg.server.id or self.server is None) is False:
            return False
        if not self.case_sensitive:
            triggered_by = triggered_by.lower()
            content = content.lower()
        if not self.regex:
            if triggered_by not in content:
                return False
        else:
            found = re.search(triggered_by, content)
            if not found:
                return False
        timestamp = datetime.datetime.now()
        passed = (timestamp - self.last_triggered).seconds
        if passed > self.cooldown:
            self.last_triggered = timestamp
            return True
        else:
            return False

    def payload(self):
        if self.responses:
            self.triggered += 1
        if self.type == "all":
            return self.responses
        elif self.type == "random":
            if self.responses:
                return [choice(self.responses)]
            else:
                return []
        else:
            raise RuntimeError("Invalid trigger type.")

    def can_edit(self, user):
        server = user.server
        admin_role = settings.get_server_admin(server)
        is_owner = user.id == settings.owner
        is_admin = discord.utils.get(user.roles, name=admin_role) is not None
        is_trigger_owner = user.id == self.owner
        trigger_is_global = self.server is None
        if trigger_is_global:
            if is_trigger_owner or is_owner:
                return True
            else:
                return False
        else:
            if is_admin or is_trigger_owner:
                return True
            else:
                return False

def check_folders():
    paths = ("data/trigger", "data/trigger/files")
    for path in paths:
        if not os.path.exists(path):
            print("Creating {} folder...".format(path))
            os.makedirs(path)

def check_files():
    f = "data/trigger/triggers.json"
    if not dataIO.is_valid_json(f):
        print("Creating empty triggers.json...")
        dataIO.save_json(f, [])

def setup(bot):
    check_folders()
    check_files()
    bot.add_cog(Trigger(bot))
