"""状态命令"""

from .base import CommandHandler
from ..session import InteractiveSession
from ..theme import PRIMARY, SUCCESS, ERROR, TEXT_MUTED, COLORS
from ..formatting import console, status_info
from rich.text import Text
from rich.style import Style


class StatusCommand(CommandHandler):
    name = "status"
    description = "显示当前配置状态"
    usage = "/status"

    def execute(self, args: str, session: InteractiveSession) -> None:
        console.print()
        header = Text()
        header.append("当前状态:", style=Style(color=PRIMARY, bold=True))
        console.print(header)
        console.print()

        api_set = bool(session.llm_config.api_key)
        topic_set = bool(session.topic)

        status_items = [
            ("API Key", api_set, "已设置" if api_set else "未设置"),
            ("议题", topic_set, session.topic if topic_set else "未设置"),
            ("预设角色", True, session.preset),
            ("模型", True, session.llm_config.model),
            ("最大轮数", True, str(session.max_rounds)),
        ]

        for label, is_ok, value in status_items:
            text = Text()
            text.append(f"  {label}: ", style=Style(color=TEXT_MUTED))
            status_icon = "✓" if is_ok else "✗"
            icon_color = SUCCESS if is_ok else ERROR
            text.append(status_icon, style=Style(color=icon_color))
            text.append(" ", style=Style(color=TEXT_MUTED))
            text.append(value, style=Style(color=COLORS.TEXT))
            console.print(text)

        console.print()

        if not api_set or not topic_set:
            missing = session.validate_config()
            if missing:
                text = Text()
                text.append("提示: ", style=Style(color=COLORS.GOLD))
                missing_str = ", ".join(missing)
                text.append(f"缺少 {missing_str}", style=Style(color=COLORS.TEXT))
                console.print(text)

                text2 = Text()
                text2.append("  ", style=Style(color=TEXT_MUTED))
                text2.append(
                    "使用 /config api_key YOUR_KEY 设置 API Key",
                    style=Style(color=TEXT_MUTED),
                )
                console.print(text2)

                text3 = Text()
                text3.append("  ", style=Style(color=TEXT_MUTED))
                text3.append(
                    "或直接输入议题文本后使用 /start 开始辩论",
                    style=Style(color=TEXT_MUTED),
                )
                console.print(text3)
        else:
            status_info("输入 /start 开始辩论")

        console.print()
