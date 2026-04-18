"""帮助命令"""

from .base import CommandHandler
from ..session import InteractiveSession
from ..theme import PRIMARY, TEXT_MUTED, SUCCESS, INFO
from ..formatting import console
from rich.text import Text
from rich.style import Style


class HelpCommand(CommandHandler):
    name = "help"
    description = "显示帮助信息"
    usage = "/help"

    def execute(self, args: str, session: InteractiveSession) -> None:
        console.print()
        header = Text()
        header.append("命令列表:", style=Style(color=PRIMARY, bold=True))
        console.print(header)
        console.print()

        commands = [
            ("/help", "显示帮助信息"),
            (
                "/config",
                "查看/配置参数 [api_key|base_url|model|max_rounds|preset|output_dir]",
            ),
            ("/presets", "显示预设角色列表"),
            ("/status", "显示当前配置状态"),
            ("/start", "启动辩论（需先设置议题）"),
            ("/quit", "退出交互模式"),
        ]

        for cmd, desc in commands:
            text = Text()
            text.append("  ", style=Style(color=TEXT_MUTED))
            text.append(cmd, style=Style(color=SUCCESS))
            text.append("  ", style=Style(color=TEXT_MUTED))
            text.append(desc, style=Style(color=INFO))
            console.print(text)

        console.print()
        usage_header = Text()
        usage_header.append("用法提示:", style=Style(color=PRIMARY, bold=True))
        console.print(usage_header)
        console.print()

        tips = [
            "- 直接输入文本可设置辩论议题",
            "- 输入 /config model gpt-4o 可修改模型",
            "- 按 Ctrl+C 可快速退出",
        ]

        for tip in tips:
            console.print(f"[{TEXT_MUTED}]  {tip}[/{TEXT_MUTED}]")

        console.print()
