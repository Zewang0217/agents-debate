"""交互式 REPL 模式"""

import sys
import signal
import asyncio
import argparse

from rich.console import Console
from rich.text import Text
from rich.style import Style

from .session import InteractiveSession
from .commands.base import CommandRegistry, parse_input
from .commands.help import HelpCommand
from .commands.config import ConfigCommand
from .commands.presets import PresetsCommand
from .commands.status import StatusCommand
from .commands.start import StartCommand
from .commands.quit import QuitCommand
from .theme import COLORS, PRIMARY, SECONDARY, TEXT_MUTED
from .formatting import print_brand_header, status_success, status_error

console = Console()

_shutdown_requested = False


def _signal_handler(signum, frame):
    """Ctrl+C 信号处理"""
    global _shutdown_requested
    _shutdown_requested = True
    console.print()
    status_success("再见！下次继续辩论吧。")
    sys.exit(0)


def _show_prompt():
    """显示命令提示符"""
    text = Text()
    text.append("debate-prd", style=Style(color=PRIMARY))
    text.append(" ❯ ", style=Style(color=SECONDARY))
    console.print(text, end="")


def _show_topic_set(topic: str):
    """显示议题设置确认"""
    text = Text()
    text.append("  ", style=Style(color=TEXT_MUTED))
    text.append("议题已设置为: ", style=Style(color=PRIMARY))
    text.append(topic, style=Style(color=COLORS.TEXT))
    console.print(text)


def run_interactive_cli(args: argparse.Namespace | None = None):
    """运行交互式 CLI"""
    signal.signal(signal.SIGINT, _signal_handler)

    session = InteractiveSession()
    session.load_from_env()

    if args:
        if args.preset:
            session.preset = args.preset
        if args.max_rounds:
            session.max_rounds = args.max_rounds
        if args.output_dir:
            session.output_dir = args.output_dir

    registry = CommandRegistry()
    registry.register(HelpCommand())
    registry.register(ConfigCommand())
    registry.register(PresetsCommand())
    registry.register(StatusCommand())
    registry.register(StartCommand())
    registry.register(QuitCommand())

    console.print()
    print_brand_header(session.llm_config.model, session.preset)
    console.print(f"[{PRIMARY}]交互模式已启动[/{PRIMARY}]")
    console.print(
        f"[{TEXT_MUTED}]输入 /help 查看可用命令，或直接输入议题文本[/{TEXT_MUTED}]"
    )
    console.print()

    while session.running:
        if _shutdown_requested:
            break

        _show_prompt()

        try:
            user_input = input().strip()
        except EOFError:
            console.print()
            status_success("再见！")
            break

        if not user_input:
            continue

        command_name, command_args = parse_input(user_input)

        if command_name == "text":
            session.topic = user_input
            _show_topic_set(user_input)
        else:
            handler = registry.get(command_name)
            if handler:
                handler.execute(command_args, session)
            else:
                status_error(f"未知命令: /{command_name}")
                console.print(f"[{TEXT_MUTED}]输入 /help 查看可用命令[/{TEXT_MUTED}]")


def parse_interactive_args() -> argparse.Namespace:
    """解析交互模式参数"""
    parser = argparse.ArgumentParser(
        description="交互式辩论配置和启动",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument("--preset", type=str, default="pm_vs_dev", help="预设角色组合")
    parser.add_argument("--max-rounds", type=int, default=6, help="辩论最大轮数")
    parser.add_argument(
        "--output-dir", type=str, default="./output", help="PRD 输出目录"
    )

    return parser.parse_args()


def main():
    """交互模式入口"""
    args = parse_interactive_args()
    run_interactive_cli(args)


if __name__ == "__main__":
    main()
