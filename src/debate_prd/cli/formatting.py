"""CLI 输出格式化工具

遵循 Rosé Pine 设计规范，使用 Rich 库实现格式化输出。
"""

from rich.console import Console
from rich.text import Text
from rich.table import Table
from rich.panel import Panel
from rich.style import Style
from rich.align import Align

from .theme import COLORS, ERROR, WARNING, SUCCESS, INFO, PRIMARY, TEXT_PRIMARY, TEXT_MUTED, SECONDARY

console = Console()


# === ASCII Art Logo ===
ASCII_LOGO = """
  ╭──────────────────────────────────────╮
  │                                      │
  │    ▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀▀    │
  │    ▐  DEBATE PRD  ▐  ⚔️ 辩论生成   │    │
  │    ▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄▄    │
  │                                      │
  │    Two Agents. One PRD. Zero BS.    │
  │                                      │
  ╰──────────────────────────────────────╯
"""


def print_logo() -> None:
    """打印品牌 Logo"""
    logo_text = Text()
    logo_text.append(ASCII_LOGO, style=Style(color=PRIMARY))
    console.print(Align.center(logo_text))
    console.print()


def status_success(message: str) -> None:
    """成功状态: [ ✓ ] 任务执行成功"""
    text = Text()
    text.append("[ ", style=Style(color=TEXT_PRIMARY))
    text.append("✓", style=Style(color=SUCCESS, bold=True))
    text.append(" ] ", style=Style(color=TEXT_PRIMARY))
    text.append(message, style=Style(color=SUCCESS))
    console.print(text)


def status_error(message: str) -> None:
    """错误状态: [ ✗ ] 找不到指定文件"""
    text = Text()
    text.append("[ ", style=Style(color=TEXT_PRIMARY))
    text.append("✗", style=Style(color=ERROR, bold=True))
    text.append(" ] ", style=Style(color=TEXT_PRIMARY))
    text.append(message, style=Style(color=ERROR))
    console.print(text)


def status_warning(message: str) -> None:
    """警告状态: [ ! ] 空间即将不足"""
    text = Text()
    text.append("[ ", style=Style(color=TEXT_PRIMARY))
    text.append("!", style=Style(color=WARNING, bold=True))
    text.append(" ] ", style=Style(color=TEXT_PRIMARY))
    text.append(message, style=Style(color=WARNING))
    console.print(text)


def status_info(message: str) -> None:
    """信息状态: [ i ] 正在下载依赖..."""
    text = Text()
    text.append("[ ", style=Style(color=TEXT_PRIMARY))
    text.append("i", style=Style(color=INFO, bold=True))
    text.append(" ] ", style=Style(color=TEXT_PRIMARY))
    text.append(message, style=Style(color=TEXT_PRIMARY))
    console.print(text)


def prompt_symbol(path: str = "~/project") -> Text:
    """Prompt 提示符: ➜ ~/project ❯ """
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