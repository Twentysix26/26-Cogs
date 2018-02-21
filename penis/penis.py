import discord
import random
from discord.ext import commands
from __main__ import send_cmd_help

class Penis:
    """Penis related commands."""

    def __init__(self, bot):
        self.bot = bot

    @commands.command(pass_context=True)
    async def penis(self, ctx, *users : discord.Member):
        """Detects user's penis length

        This is 100% accurate."""
        if len(users) == 0:
            await send_cmd_help(ctx)
            return
        
        state = random.getstate()
        user_dongs = []
        longest = max(len(user.name) for user in users) # So we can neatly line up the dongs
        for user in users:          
            random.seed(user.id)
            dong = "8{}D".format("=" * random.randint(0, 30))
            user_dongs.append("Size of {1:<{0}} {2}".format(longest + 1, user.name + ":", dong))
        random.setstate(state)
        
        await self.bot.say("\n".join(user_dongs))


def setup(bot):
    bot.add_cog(Penis(bot))
