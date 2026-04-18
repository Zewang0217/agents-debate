"""预设角色命令"""

from .base import CommandHandler
from ..session import InteractiveSession
from ...config.presets import DEBATER_PRESETS
from ..theme import PRIMARY, SUCCESS, TEXT_MUTED, COLORS
from ..formatting import console
from rich.text import Text
from rich.style import Style


class PresetsCommand(CommandHandler):
    name = "presets"
    description = "显示预设角色列表"
    usage = "/presets [preset_name]"

    def execute(self, args: str, session: InteractiveSession) -> None:
        console.print()
        header = Text()
        header.append("可用预设角色:", style=Style(color=PRIMARY, bold=True))
        console.print(header)
        console.print()

        for preset_name, config in DEBATER_PRESETS.items():
            text = Text()
            current_marker = "●" if preset_name == session.preset else " "
            text.append(
                f"  {current_marker} ",
                style=Style(
                    color=SUCCESS if preset_name == session.preset else TEXT_MUTED
                ),
            )
            text.append(
                preset_name,
                style=Style(
                    color=PRIMARY if preset_name == session.preset else COLORS.TEXT,
                    bold=(preset_name == session.preset),
                ),
            )
            console.print(text)

            d1 = config["debater1"]
            d2 = config["debater2"]

            desc1 = Text()
            desc1.append(f"      {d1['role']}", style=Style(color=COLORS.FOAM))
            desc1.append(f" ({d1['stance'][:30]}...)", style=Style(color=TEXT_MUTED))
            console.print(desc1)

            desc2 = Text()
            desc2.append(f"      {d2['role']}", style=Style(color=COLORS.IRIS))
            desc2.append(f" ({d2['stance'][:30]}...)", style=Style(color=TEXT_MUTED))
            console.print(desc2)

            console.print()

        text = Text()
        text.append("当前使用: ", style=Style(color=TEXT_MUTED))
        text.append(session.preset, style=Style(color=SUCCESS))
        console.print(text)

        console.print()

        hint = Text()
        hint.append("切换预设: ", style=Style(color=TEXT_MUTED))
        hint.append("/config preset pm_vs_dev", style=Style(color=PRIMARY))
        console.print(hint)
        console.print()
