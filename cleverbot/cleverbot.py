from cleverwrap import CleverWrap as _CleverWrap
from discord.ext import commands
from cogs.utils import checks
from .utils.dataIO import dataIO
import os
import asyncio


class Cleverbot():
    """Cleverbot"""

    def __init__(self, bot):
        self.bot = bot
        self.settings = dataIO.load_json("data/cleverbot/settings.json")
        self.clv = _CleverWrap(self.settings["key"])

    @commands.group(no_pm=True, invoke_without_command=True, pass_context=True)
    async def cleverbot(self, ctx, *, message):
        """Talk with cleverbot"""
        result = await self.get_response(message)
        await self.bot.say(result)

    @cleverbot.command()
    @checks.is_owner()
    async def toggle(self):
        """Toggles reply on mention"""
        self.settings["TOGGLE"] = not self.settings["TOGGLE"]
        if self.settings["TOGGLE"]:
            await self.bot.say("I will reply on mention.")
        else:
            await self.bot.say("I won't reply on mention anymore.")
        dataIO.save_json("data/cleverbot/settings.json", self.settings)

    async def get_response(self, msg):
        question = self.bot.loop.run_in_executor(None, self.clv.say, msg)
        try:
            answer = await asyncio.wait_for(question, timeout=10)
        except asyncio.TimeoutError:
            answer = "We'll talk later..."
        return answer

    async def on_message(self, message):
        if not self.settings["TOGGLE"] or message.channel.is_private:
            return

        if not self.bot.user_allowed(message):
            return

        if message.author.id != self.bot.user.id:
            mention = message.server.me.mention
            if message.content.startswith(mention):
                content = message.content.replace(mention, "").strip()
                await self.bot.send_typing(message.channel)
                response = await self.get_response(content)
                await self.bot.send_message(message.channel, response)

    @cleverbot.command()
    @checks.is_owner()
    async def apikey(self, key: str):
        """Sets credentials to be used with cleverbot.com

        You can get them from https://cleverbot.com/api
        Use this command in direct message to keep your
        credentials secret"""
        self.settings["key"] = key
        dataIO.save_json("data/cleverbot/settings.json", self.settings)
        await self.bot.say("Credentials set.")


def check_folders():
    if not os.path.exists("data/cleverbot"):
        print("Creating data/cleverbot folder...")
        os.makedirs("data/cleverbot")


def check_files():
    f = "data/cleverbot/settings.json"
    data = {"TOGGLE" : True, "key" : ""}
    if not dataIO.is_valid_json(f):
        dataIO.save_json(f, data)


def setup(bot):
    if _CleverWrap is False:
        raise RuntimeError("CleverWrap is not installed. "
                           "Run[p]debug bot.pip_install('cleverwrap')\n"
                           "and restart Red once you get a response.\n"
                           "Then [p]load cleverbot")
    check_folders()
    check_files()
    bot.add_cog(Cleverbot(bot))
