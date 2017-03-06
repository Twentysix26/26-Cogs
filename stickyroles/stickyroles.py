import discord
import os
from discord.ext import commands
from collections import defaultdict
from .utils.dataIO import dataIO
from .utils import checks

default = {
    "sticky_roles": [],
    "to_reapply"  : {}
}


class StickyRoles:
    """Reapplies specific roles on join"""

    def __init__(self, bot):
        self.bot = bot
        db = dataIO.load_json("data/stickyroles/stickyroles.json")
        self.db = defaultdict(lambda: default.copy(), db)

    @commands.group(pass_context=True, aliases=["stickyrole"])
    @checks.admin()
    async def stickyroles(self, ctx):
        """Adds / removes roles to be reapplied on join"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @stickyroles.command(pass_context=True)
    async def add(self, ctx, *, role: discord.Role):
        """Adds role to be reapplied on join"""
        server = ctx.message.server
        if not server.me.top_role.position > role.position:
            await self.bot.say("I don't have enough permissions to add that "
                               "role. Remember to take role hierarchy in "
                               "consideration.")
            return
        self.db[server.id]["sticky_roles"].append(role.id)
        self.save()
        await self.bot.say("That role will now be reapplied on join.")

    @stickyroles.command(pass_context=True)
    async def remove(self, ctx, *, role: discord.Role):
        """Removes role to be reapplied on join"""
        server = ctx.message.server
        try:
            self.db[server.id]["sticky_roles"].remove(role.id)
        except ValueError:
            await self.bot.say("That role was never added in the first place.")
        else:
            self.save()
            await self.bot.say("That role won't be reapplied on join.")

    @stickyroles.command(pass_context=True)
    async def clear(self, ctx):
        """Removes all sticky roles"""
        server = ctx.message.server
        try:
            del self.db[server.id]
        except KeyError:
            pass
        self.save()
        await self.bot.say("All sticky roles have been removed.")

    @stickyroles.command(name="list", pass_context=True)
    async def _list(self, ctx):
        """Lists sticky roles"""
        server = ctx.message.server
        roles = self.db[server.id].get("sticky_roles", [])
        roles = [discord.utils.get(server.roles, id=r) for r in roles]
        roles = [r.name for r in roles if r is not None]
        if roles:
            await self.bot.say("Sticky roles:\n\n" + ", ".join(roles))
        else:
            await self.bot.say("No sticky roles. Add some with `{}stickyroles "
                               "add`".format(ctx.prefix))

    async def on_member_remove(self, member):
        server = member.server
        if server.id not in self.db:
            return

        save = False
        settings = self.db[server.id]

        for role in member.roles:
            if role.id in settings["sticky_roles"]:
                if member.id not in settings["to_reapply"]:
                    settings["to_reapply"][member.id] = []
                settings["to_reapply"][member.id].append(role.id)
                save = True

        if save:
            self.save()

    async def on_member_join(self, member):
        server = member.server
        if server.id not in self.db:
            return

        settings = self.db[server.id]

        if member.id not in settings["to_reapply"]:
            return

        to_add = []

        for role_id in settings["to_reapply"][member.id]:
            if role_id not in settings["sticky_roles"]:
                continue
            role = discord.utils.get(server.roles, id=role_id)
            if role:
                to_add.append(role)

        del settings["to_reapply"][member.id]

        if to_add:
            try:
                await self.bot.add_roles(member, *to_add)
            except discord.Forbidden:
                print("Failed to add roles to {} ({})\n{}\n"
                      "I lack permissions to do that."
                      "".format(member, member.id, to_add))
            except discord.HTTPException as e:
                print("Failed to add roles to {} ({})\n{}\n"
                      "{}"
                      "".format(member, member.id, to_add, e))

        self.save()

    def save(self):
        dataIO.save_json("data/stickyroles/stickyroles.json", self.db)


def check_folders():
    if not os.path.exists("data/stickyroles"):
        print("Creating data/stickyroles folder...")
        os.makedirs("data/stickyroles")


def check_files():
    if not dataIO.is_valid_json("data/stickyroles/stickyroles.json"):
        print("Creating empty stickyroles.json...")
        dataIO.save_json("data/stickyroles/stickyroles.json", {})


def setup(bot):
    check_folders()
    check_files()
    bot.add_cog(StickyRoles(bot))