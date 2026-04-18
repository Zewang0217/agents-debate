"""配置命令"""

from .base import CommandHandler
from ..session import InteractiveSession
from ...config.presets import list_presets
from ..theme import PRIMARY, SUCCESS, ERROR, TEXT_MUTED, COLORS
from ..formatting import console, status_success, status_error
from rich.text import Text
from rich.style import Style


class ConfigCommand(CommandHandler):
    name = "config"
    description = "查看/配置参数"
    usage = "/config [key] [value]"

    def execute(self, args: str, session: InteractiveSession) -> None:
        parts = args.split(maxsplit=1) if args else []

        if not parts:
            self._show_all_config(session)
            return

        key = parts[0].lower()

        if len(parts) == 1:
            self._show_single_config(key, session)
        else:
            value = parts[1]
            self._set_config(key, value, session)

    def _show_all_config(self, session: InteractiveSession) -> None:
        console.print()
        header = Text()
        header.append("当前配置:", style=Style(color=PRIMARY, bold=True))
        console.print(header)
        console.print()

        display = session.to_display_dict()

        items = [
            ("api_key", display["api_key"], display["api_key_set"]),
            ("base_url", display["base_url"], True),
            ("model", display["model"], True),
            ("preset", display["preset"], True),
            ("max_rounds", display["max_rounds"], True),
            ("output_dir", display["output_dir"], True),
        ]

        for key, value, is_set in items:
            text = Text()
            text.append(f"  {key}: ", style=Style(color=TEXT_MUTED))
            if key == "api_key":
                status_icon = "✓" if is_set else "✗"
                icon_color = SUCCESS if is_set else ERROR
                text.append(f"{value} ", style=Style(color=COLORS.TEXT))
                text.append(f"({status_icon})", style=Style(color=icon_color))
            else:
                text.append(value, style=Style(color=COLORS.TEXT))
            console.print(text)

        console.print()

        hint = Text()
        hint.append("修改配置: ", style=Style(color=TEXT_MUTED))
        hint.append("/config model gpt-4o", style=Style(color=PRIMARY))
        console.print(hint)
        console.print()

    def _show_single_config(self, key: str, session: InteractiveSession) -> None:
        valid_keys = [
            "api_key",
            "base_url",
            "model",
            "preset",
            "max_rounds",
            "output_dir",
        ]

        if key not in valid_keys:
            status_error(f"未知配置项: {key}")
            console.print(
                f"[{TEXT_MUTED}]可用配置项: {', '.join(valid_keys)}[/{TEXT_MUTED}]"
            )
            return

        display = session.to_display_dict()

        if key == "api_key":
            status_success(
                f"API Key: {display['api_key']} ({'已设置' if display['api_key_set'] else '未设置'})"
            )
        else:
            status_success(f"{key}: {display.get(key, '(未设置)')}")

    def _set_config(self, key: str, value: str, session: InteractiveSession) -> None:
        if key == "preset" and value not in list_presets():
            status_error(f"无效预设: {value}")
            console.print(
                f"[{TEXT_MUTED}]可用预设: {', '.join(list_presets())}[/{TEXT_MUTED}]"
            )
            return

        if session.set_config(key, value):
            status_success(f"{key} 已设置为: {value}")
        else:
            status_error(f"设置失败: {key}")
            if key == "max_rounds":
                console.print(f"[{TEXT_MUTED}]max_rounds 必须为整数[/{TEXT_MUTED}]")
