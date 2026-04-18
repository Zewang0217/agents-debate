"""CLI 输出格式化工具

遵循 Rosé Pine 设计规范，使用 Rich 库实现格式化输出。
"""

from rich.console import Console
from rich.text import Text
from rich.table import Table
from rich.panel import Panel
from rich.style import Style
from rich.align import Align

from .theme import (
    COLORS,
    ERROR,
    WARNING,
    SUCCESS,
    INFO,
    PRIMARY,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
    TEXT_MUTED,
    SECONDARY,
)

console = Console()


BRAND_LOGO = """
    ╭─────────────────────────────────────╮
    │                                     │
    │   🌹  DEBATE PRD                    │
    │   ─────────────────                 │
    │   Two Agents. One PRD. Zero BS.     │
    │                                     │
    ╰─────────────────────────────────────╯
"""

BRAND_TAGLINE = "辩论式 PRD 生成系统"


def print_brand_header(model: str = "", preset: str = "") -> None:
    """打印品牌标识头部"""
    logo_text = Text()
    logo_text.append(BRAND_LOGO, style=Style(color=PRIMARY))
    console.print(Align.center(logo_text))

    tagline_text = Text()
    tagline_text.append(BRAND_TAGLINE, style=Style(color=TEXT_SECONDARY))
    console.print(Align.center(tagline_text))
    console.print()

    if model:
        info_text = Text()
        info_text.append("模型: ", style=Style(color=PRIMARY))
        info_text.append(model, style=Style(color=TEXT_PRIMARY))
        console.print(info_text)

    if preset:
        preset_text = Text()
        preset_text.append("预设: ", style=Style(color=PRIMARY))
        preset_text.append(preset, style=Style(color=TEXT_PRIMARY))
        console.print(preset_text)

    hint_text = Text()
    hint_text.append("按 Ctrl+C 可随时退出", style=Style(color=TEXT_SECONDARY))
    console.print(hint_text)
    console.print()


def phase_separator(phase: str) -> None:
    """打印阶段切换分隔线"""
    console.print()
    text = Text()
    text.append("━━━ ", style=Style(color=TEXT_MUTED))
    text.append(f"阶段: {phase}", style=Style(color=PRIMARY, bold=True))
    text.append(" ━━━", style=Style(color=TEXT_MUTED))
    console.print(text)
    console.print()


def status_success(message: str) -> None:
    """成功状态: [ ✓ ] 任务执行成功"""
    text = Text()
    text.append("[ ", style=Style(color=SUCCESS))
    text.append("✓", style=Style(color=SUCCESS, bold=True))
    text.append(" ] ", style=Style(color=SUCCESS))
    text.append(message, style=Style(color=TEXT_PRIMARY))
    console.print(text)


def status_error(message: str) -> None:
    """错误状态: [ ✗ ] 找不到指定文件"""
    text = Text()
    text.append("[ ", style=Style(color=ERROR))
    text.append("✗", style=Style(color=ERROR, bold=True))
    text.append(" ] ", style=Style(color=ERROR))
    text.append(message, style=Style(color=TEXT_PRIMARY))
    console.print(text)


def status_warning(message: str) -> None:
    """警告状态: [ ! ] 空间即将不足"""
    text = Text()
    text.append("[ ", style=Style(color=WARNING))
    text.append("!", style=Style(color=WARNING, bold=True))
    text.append(" ] ", style=Style(color=WARNING))
    text.append(message, style=Style(color=TEXT_PRIMARY))
    console.print(text)


def status_info(message: str) -> None:
    """信息状态: [ i ] 正在下载依赖..."""
    text = Text()
    text.append("[ ", style=Style(color=INFO))
    text.append("i", style=Style(color=INFO, bold=True))
    text.append(" ] ", style=Style(color=INFO))
    text.append(message, style=Style(color=TEXT_PRIMARY))
    console.print(text)


def prompt_symbol(path: str = "~/project") -> Text:
    """Prompt 提示符: ➜ ~/project ❯"""
    text = Text()
    text.append("➜ ", style=Style(color=PRIMARY))
    text.append(path, style=Style(color=INFO))
    text.append(" ❯ ", style=Style(color=COLORS.ROSE))
    return text


def create_table(title: str, headers: list[str]) -> Table:
    """创建 Rosé Pine 风格表格"""
    table = Table(
        title=title,
        title_style=Style(color=PRIMARY, bold=True),
        border_style=Style(color=TEXT_MUTED),
        header_style=Style(color=PRIMARY, bold=True),
        show_header=True,
    )
    for header in headers:
        table.add_column(header, style=Style(color=TEXT_PRIMARY))
    return table


def print_panel(content: str, title: str = "", border_color: str = PRIMARY) -> None:
    """打印带边框的面板"""
    panel = Panel(
        content,
        title=title,
        border_style=Style(color=border_color),
    )
    console.print(panel)


def print_header(title: str) -> None:
    """打印标题头"""
    console.print()
    text = Text()
    text.append("━" * 20 + " ", style=Style(color=TEXT_MUTED))
    text.append(title, style=Style(color=PRIMARY, bold=True))
    text.append(" " + "━" * 20, style=Style(color=TEXT_MUTED))
    console.print(text)
    console.print()


def print_kv(key: str, value: str, key_color: str = PRIMARY) -> None:
    """打印键值对"""
    text = Text()
    text.append(f"{key}: ", style=Style(color=key_color))
    text.append(value, style=Style(color=TEXT_PRIMARY))
    console.print(text)
