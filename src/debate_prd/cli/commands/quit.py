"""退出命令"""

from .base import CommandHandler
from ..session import InteractiveSession
from ..theme import SUCCESS
from ..formatting import console, status_success


class QuitCommand(CommandHandler):
    name = "quit"
    description = "退出交互模式"
    usage = "/quit"

    def execute(self, args: str, session: InteractiveSession) -> None:
        console.print()
        status_success("再见！下次继续辩论吧。")
        session.running = False
