"""命令行入口 - Rosé Pine 风格"""

import argparse
import asyncio
import sys
import os
import signal

from rich.console import Console
from rich.markdown import Markdown

from ..config.presets import list_presets
from ..config.settings import Settings, LLMConfig
from ..output.prd_generator import PRDGenerator
from .formatting import status_success, status_error, status_warning, print_panel
from .theme import COLORS, PRIMARY

console = Console()

# 全局退出标志
_shutdown_requested = False


def _signal_handler(signum, frame):
    """信号处理器 - Ctrl+C"""
    global _shutdown_requested
    _shutdown_requested = True
    console.print()
    console.print(f"[{COLORS.GOLD}]⚠ 收到退出信号，正在优雅退出...[/{COLORS.GOLD}]")


def _get_role_colors(role: str) -> tuple[str, str]:
    """获取角色颜色"""
    if role == "PM":
        return (COLORS.IRIS, f"bold {COLORS.IRIS}")
    elif role == "Dev":
        return (COLORS.GOLD, f"bold {COLORS.GOLD}")
    elif role == "Moderator":
        return (COLORS.PINE, f"bold {COLORS.PINE}")
    else:
        return (COLORS.TEXT, f"bold {COLORS.TEXT}")


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="辩论式 PRD 生成系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  debate-prd --topic "用户认证系统" --preset pm_vs_dev

环境变量:
  OPENAI_API_KEY  - API Key
  OPENAI_BASE_URL - API Base URL (默认: https://api.openai.com/v1)
  OPENAI_MODEL    - 模型名称 (默认: gpt-4o-mini)
        """,
    )

    parser.add_argument(
        "--api-key", type=str, default=os.environ.get("OPENAI_API_KEY", "")
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
    )
    parser.add_argument(
        "--model", type=str, default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
    )
    parser.add_argument("--max-rounds", type=int, default=6)
    parser.add_argument(
        "--preset", type=str, choices=list_presets(), default="pm_vs_dev"
    )
    parser.add_argument("--topic", type=str, default=None)
    parser.add_argument("--output-dir", type=str, default="./output")

    return parser.parse_args()


def main():
    """命令行主入口"""
    signal.signal(signal.SIGINT, _signal_handler)

    args = parse_args()

    if not args.api_key:
        console.print(f"[{COLORS.LOVE}]错误: 未提供 API Key[/{COLORS.LOVE}]")
        console.print(
            f"[{COLORS.TEXT}]请通过 --api-key 参数或 OPENAI_API_KEY 环境变量设置[/{COLORS.TEXT}]"
        )
        sys.exit(1)

    console.print()
    console.print(f"[{PRIMARY}]模型:[/{PRIMARY}] {args.model}")
    console.print(f"[{PRIMARY}]预设:[/{PRIMARY}] {args.preset}")
    console.print(f"[{COLORS.SUBTLE}]按 Ctrl+C 可随时退出[/{COLORS.SUBTLE}]")
    console.print()

    llm_config = LLMConfig(
        api_key=args.api_key, base_url=args.base_url, model=args.model
    )
    topic = args.topic or _input_topic()

    asyncio.run(
        run_debate(llm_config, args.preset, topic, args.max_rounds, args.output_dir)
    )


def _input_topic() -> str:
    """交互输入议题"""
    console.print(f"[{COLORS.IRIS}]请输入辩论议题:[/{COLORS.IRIS}]")
    topic = input("> ").strip()
    return topic or "通用产品需求"


async def run_debate(
    llm_config: LLMConfig, preset: str, topic: str, max_rounds: int, output_dir: str
):
    """运行辩论"""
    console.print()
    console.print(f"[{COLORS.IRIS}]议题: {topic}[/{COLORS.IRIS}]")
    console.print(f"[{COLORS.TEXT}]预设: {preset}[/{COLORS.TEXT}]")
    console.print(f"[{COLORS.MUTED}]" + "-" * 40 + f"[/{COLORS.MUTED}]")

    moderator = None
    current_role_state = {"role": ""}

    try:
        from openai import AsyncOpenAI

        client = AsyncOpenAI(api_key=llm_config.api_key, base_url=llm_config.base_url)
        client.model = llm_config.model

        settings = Settings(llm=llm_config, max_rounds=max_rounds)

        from ..core.debate_loop import DebateModerator, create_debater_pair
        from ..core.messaging.mailbox import reset_message_router

        reset_message_router()

        debater1, debater2 = create_debater_pair(
            llm_client=client, preset_name=preset, memory_scope="project"
        )
        moderator = DebateModerator(
            debater1=debater1, debater2=debater2, llm_client=client, settings=settings
        )

        # 主事件循环
        async for event in moderator.run_full_debate_stream(topic):
            if _shutdown_requested:
                _handle_graceful_exit(moderator, preset, topic, output_dir)
                return

            event_type = event.get("type", "")

            if event_type == "phase_start":
                console.print()
                print_panel(
                    f"进入 {event.get('phase', '')} 阶段",
                    title="阶段切换",
                    border_color=COLORS.IRIS,
                )

            elif event_type == "ask":
                # 进入澄清问答循环
                result = await _clarification_loop(
                    moderator, event, preset, topic, output_dir, current_role_state
                )
                if result == "done":
                    return
                # 如果是 "continue"，继续主循环处理辩论阶段

            elif event_type == "prd_generated":
                console.print()
                status_success("PRD基础版生成完成")

            elif event_type == "clarification_done":
                console.print()
                status_success("澄清阶段完成")
                console.print(f"[{COLORS.MUTED}]" + "-" * 40 + f"[/{COLORS.MUTED}]")

            elif event_type == "debate_complete":
                _show_complete(event, preset, topic, output_dir)
                return

            elif event_type == "token":
                _print_token(event, current_role_state, console)

            elif event_type == "message_complete":
                _print_complete(console)

            elif event_type == "moderator":
                console.print()
                console.print(
                    f"[{COLORS.PINE}]● Moderator:[/{COLORS.PINE}] {event.get('content', '')}"
                )

            elif event_type == "error":
                status_error(event.get("message", "错误"))
                return

    except KeyboardInterrupt:
        _handle_graceful_exit(moderator, preset, topic, output_dir)
    except asyncio.CancelledError:
        _handle_graceful_exit(moderator, preset, topic, output_dir)


async def _clarification_loop(
    moderator, first_event, preset, topic, output_dir, current_role_state
):
    """澄清阶段问答循环 - 使用 while 循环持续问答"""
    event = first_event

    while True:
        if _shutdown_requested:
            _handle_graceful_exit(moderator, preset, topic, output_dir)
            return "done"

        # 显示问题并获取回答
        question = event.get("question", "")
        console.print()
        console.print(f"[{COLORS.PINE}]● Moderator:[/{COLORS.PINE}] {question}")
        console.print(f"[{COLORS.IRIS}]你的回答:[/{COLORS.IRIS}]", end=" ")
        answer = await asyncio.to_thread(input)
        moderator.submit_user_answer(answer)

        # 继续澄清，获取下一个事件
        found_ask = False
        async for e in moderator.resume_clarification():
            t = e.get("type", "")

            if t == "ask":
                # 找到下一个问题，继续循环
                event = e
                found_ask = True
                break

            elif t == "prd_generated":
                console.print()
                status_success("PRD基础版生成完成")

            elif t == "clarification_done":
                # 澄清完成，继续消费辩论阶段事件（不退出循环）
                console.print()
                status_success("澄清阶段完成")
                console.print(f"[{COLORS.MUTED}]" + "-" * 40 + f"[/{COLORS.MUTED}]")

            elif t == "phase_start":
                # 辩论阶段开始
                console.print()
                print_panel(
                    f"进入 {e.get('phase', '')} 阶段",
                    title="阶段切换",
                    border_color=COLORS.IRIS,
                )

            elif t == "debate_complete":
                # 辩论完成
                _show_complete(e, preset, topic, output_dir)
                return "done"

            elif t == "token":
                _print_token(e, current_role_state, console)

            elif t == "message_complete":
                _print_complete(console)

            elif t == "moderator":
                console.print()
                console.print(
                    f"[{COLORS.PINE}]● Moderator:[/{COLORS.PINE}] {e.get('content', '')}"
                )

            elif t == "error":
                status_error(e.get("message", "错误"))
                return "done"

        # 检查是否找到了下一个 ask
        if found_ask:
            continue  # 继续 while 循环，等待下一个回答

        # 循环自然结束（resume_clarification 没有返回更多事件）
        return "done"


def _handle_graceful_exit(moderator, preset: str, topic: str, output_dir: str):
    """处理优雅退出"""
    console.print()
    console.print(f"[{COLORS.GOLD}]⚠ 用户中断辩论[/{COLORS.GOLD}]")

    if moderator and hasattr(moderator, "_prd_base") and moderator._prd_base:
        console.print(f"[{COLORS.TEXT}]正在保存当前进度...[/{COLORS.TEXT}]")
        generator = PRDGenerator(output_dir=output_dir)
        generator.save_string(moderator._prd_base, preset, topic + "_partial")
        console.print(f"[{COLORS.PINE}]✓ 进度已保存[/{COLORS.PINE}]")

    console.print()
    console.print(f"[{COLORS.SUBTLE}]再见！下次继续辩论吧。[/{COLORS.SUBTLE}]")


def _print_token(event: dict, state: dict, console: Console):
    """打印 token - 流式输出"""
    delta = event.get("delta", "")
    role = event.get("role", "")
    current_role = state["role"]

    if role != current_role:
        console.print()
        tc, pc = _get_role_colors(role)
        console.print(f"[{pc}]【{role}】[/{pc}]", end="")
        state["role"] = role

    tc, _ = _get_role_colors(role)
    console.print(f"[{tc}]{delta}[/{tc}]", end="")

    # 强制刷新输出缓冲区，实现真正的流式效果
    console.file.flush()


def _print_complete(console: Console):
    """打印完成标记"""
    console.print()
    console.print(f"[{COLORS.SUBTLE}]✓ 完成[/{COLORS.SUBTLE}]")
    console.print(f"[{COLORS.MUTED}]" + "-" * 40 + f"[/{COLORS.MUTED}]")


def _show_complete(event: dict, preset: str, topic: str, output_dir: str):
    """显示完成"""
    console.print()
    status_success(f"辩论完成，共 {event.get('rounds', 0)} 轮")
    console.print(Markdown(event.get("prd", "")), style=COLORS.TEXT)
    generator = PRDGenerator(output_dir=output_dir)
    generator.save_string(event.get("prd", ""), preset, topic)
    console.print()
    status_success("PRD 已保存")


if __name__ == "__main__":
    main()
