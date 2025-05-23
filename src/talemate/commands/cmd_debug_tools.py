import asyncio
import json
import logging

import structlog

from talemate.commands.base import TalemateCommand
from talemate.commands.manager import register
from talemate.prompts.base import set_default_sectioning_handler
from talemate.instance import get_agent

__all__ = [
    "CmdDebugOn",
    "CmdDebugOff",
    "CmdPromptChangeSectioning",
    "CmdRunAutomatic",
    "CmdSummarizerUpdatedLayeredHistory",
    "CmdSummarizerResetLayeredHistory",
]

log = structlog.get_logger("talemate.commands.cmd_debug_tools")


@register
class CmdDebugOn(TalemateCommand):
    """
    Command class for the 'debug_on' command
    """

    name = "debug_on"
    description = "Turn on debug mode"
    aliases = []

    async def run(self):
        logging.getLogger().setLevel(logging.DEBUG)
        await asyncio.sleep(0)


@register
class CmdDebugOff(TalemateCommand):
    """
    Command class for the 'debug_off' command
    """

    name = "debug_off"
    description = "Turn off debug mode"
    aliases = []

    async def run(self):
        logging.getLogger().setLevel(logging.INFO)
        await asyncio.sleep(0)


@register
class CmdPromptChangeSectioning(TalemateCommand):
    """
    Command class for the '_prompt_change_sectioning' command
    """

    name = "_prompt_change_sectioning"
    description = "Change the sectioning handler for the prompt system"
    aliases = []

    async def run(self):
        if not self.args:
            self.emit("system", "You must specify a sectioning handler")
            return

        handler_name = self.args[0]

        set_default_sectioning_handler(handler_name)

        self.emit("system", f"Sectioning handler set to {handler_name}")
        await asyncio.sleep(0)


@register
class CmdRunAutomatic(TalemateCommand):
    """
    Command class for the 'run_automatic' command
    """

    name = "run_automatic"
    description = "Will make the player character AI controlled for n turns"
    aliases = ["auto"]

    async def run(self):
        if self.args:
            turns = int(self.args[0])
        else:
            turns = 10

        self.emit("system", f"Making player character AI controlled for {turns} turns")
        self.scene.get_player_character().actor.ai_controlled = turns


@register
class CmdLongTermMemoryStats(TalemateCommand):
    """
    Command class for the 'long_term_memory_stats' command
    """

    name = "long_term_memory_stats"
    description = "Show stats for the long term memory"
    aliases = ["ltm_stats"]

    async def run(self):
        memory = self.scene.get_helper("memory").agent

        count = await memory.count()
        db_name = memory.db_name

        self.emit(
            "system",
            f"Long term memory for {self.scene.name} has {count} entries in the {db_name} database",
        )


@register
class CmdLongTermMemoryReset(TalemateCommand):
    """
    Command class for the 'long_term_memory_reset' command
    """

    name = "long_term_memory_reset"
    description = "Reset the long term memory"
    aliases = ["ltm_reset"]

    async def run(self):
        await self.scene.commit_to_memory()

        self.emit("system", f"Long term memory for {self.scene.name} has been reset")


@register
class CmdSetContentContext(TalemateCommand):
    """
    Command class for the 'set_content_context' command
    """

    name = "set_content_context"
    description = "Set the content context for the scene"
    aliases = ["set_context"]

    async def run(self):
        if not self.args:
            self.emit("system", "You must specify a context")
            return

        context = self.args[0]

        self.scene.context = context

        self.emit("system", f"Content context set to {context}")


@register
class CmdDumpHistory(TalemateCommand):
    """
    Command class for the 'dump_history' command
    """

    name = "dump_history"
    description = "Dump the history of the scene"
    aliases = []

    async def run(self):
        for entry in self.scene.history:
            log.debug("dump_history", entry=entry)


@register
class CmdDumpSceneSerialization(TalemateCommand):
    """
    Command class for the 'dump_scene_serialization' command
    """

    name = "dump_scene_serialization"
    description = "Dump the scene serialization"
    aliases = []

    async def run(self):
        log.debug("dump_scene_serialization", serialization=self.scene.json)

@register
class CmdSummarizerUpdatedLayeredHistory(TalemateCommand):
    """
    Command class for the 'summarizer_updated_layered_history' command
    """

    name = "summarizer_updated_layered_history"
    description = "Update the stepped archive for the summarizer"
    aliases = ["update_layered_history"]

    async def run(self):
        summarizer = get_agent("summarizer")

        await summarizer.summarize_to_layered_history()
        
@register
class CmdSummarizerResetLayeredHistory(TalemateCommand):
    """
    Command class for the 'summarizer_reset_layered_history' command
    """

    name = "summarizer_reset_layered_history"
    description = "Reset the stepped archive for the summarizer"
    aliases = ["reset_layered_history"]

    async def run(self):
        summarizer = get_agent("summarizer")
        
        # if arg is provided remove the last n layers
        if self.args:
            n = int(self.args[0])
            self.scene.layered_history = self.scene.layered_history[:-n]
        else:
            self.scene.layered_history = []
        
        await summarizer.summarize_to_layered_history()
        
@register
class CmdSummarizerContextInvestigation(TalemateCommand):
    """
    Command class for the 'summarizer_context_investigation' command
    """

    name = "summarizer_context_investigation"
    description = "Investigate the context of the scene"
    aliases = ["ctx_inv"]

    async def run(self):
        summarizer = get_agent("summarizer")

        #     async def investigate_context(self, layer:int, index:int, query:str, analysis:str="", max_calls:int=3) -> str:
        if not self.args:
            self.emit("system", "You must specify a query")
            return
        
        await summarizer.request_context_investigations(self.args[0], max_calls=1)
        