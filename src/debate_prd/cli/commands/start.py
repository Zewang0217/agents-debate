"""启动辩论命令"""

import asyncio
import sys

from .base import CommandHandler
from ..session import InteractiveSession
from ..theme import PRIMARY, ERROR, TEXT_MUTED, COLORS
from ..formatting import (
    console,
    status_error,
    status_success,
    status_warning,
    print_brand_header,
)
from rich.text import Text
from rich.style import Style


class StartCommand(CommandHandler):
    name = "start"
    description = "启动辩论"
    usage = "/start"

    def execute(self, args: str, session: InteractiveSession) -> None:
        missing = session.validate_config()

        if missing:
            status_error("无法启动辩论")
            for item in missing:
                console.print(f"[{ERROR}]  ✗ {item}[/{ERROR}]")
            console.print()
            hint = Text()
            hint.append("提示: ", style=Style(color=COLORS.GOLD))
            hint.append("先设置 API Key 和议题后再启动", style=Style(color=COLORS.TEXT))
            console.print(hint)
            return

        console.print()
        status_success("正在启动辩论...")
        console.print()

        info = Text()
        info.append("议题: ", style=Style(color=PRIMARY))
        info.append(session.topic, style=Style(color=COLORS.TEXT, bold=True))
        console.print(info)

        info2 = Text()
        info2.append("预设: ", style=Style(color=TEXT_MUTED))
        info2.append(session.preset, style=Style(color=COLORS.TEXT))
        info2.append("  |  ", style=Style(color=TEXT_MUTED))
        info2.append("模型: ", style=Style(color=TEXT_MUTED))
        info2.append(session.llm_config.model, style=Style(color=COLORS.TEXT))
        info2.append("  |  ", style=Style(color=TEXT_MUTED))
        info2.append("轮数: ", style=Style(color=TEXT_MUTED))
        info2.append(str(session.max_rounds), style=Style(color=COLORS.TEXT))
        console.print(info2)

        console.print()
        console.print(f"[{TEXT_MUTED}]{'━' * 40}[/{TEXT_MUTED}]")
        console.print()

        try:
            asyncio.run(self._run_debate(session))
        except KeyboardInterrupt:
            console.print()
            status_warning("辩论被用户中断")
        except Exception as e:
            status_error(f"辩论执行错误: {e}")

    async def _run_debate(self, session: InteractiveSession) -> None:
        """执行辩论"""
        from ..main import run_debate

        await run_debate(
            session.llm_config,
            session.preset,
            session.topic,
            session.max_rounds,
            session.output_dir,
        )
