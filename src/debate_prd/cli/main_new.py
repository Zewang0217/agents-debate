"""CLI 事件处理函数"""

import asyncio
from rich.console import Console
from rich.markdown import Markdown

from .formatting import (
    status_success, status_error, status_warning, status_info,
    print_panel, print_kv,
)
from .theme import COLORS, WARNING
from ..output.prd_generator import PRDGenerator


def _get_role_colors(role: str) -> tuple[str, str]:
    """获取角色颜色样式 - Rosé Pine 风格"""
    from .theme import COLORS
    if role == "PM":
        return (COLORS.IRIS, f"bold {COLORS.IRIS}")
    elif role == "Dev":
        return (COLORS.GOLD, f"bold {COLORS.GOLD}")
    elif role == "Business":
        return (COLORS.FOAM, f"bold {COLORS.FOAM}")
    elif role == "Security":
        return (COLORS.LOVE, f"bold {COLORS.LOVE}")
    elif role == "UX":
        return (COLORS.ROSE, f"bold {COLORS.ROSE}")
    elif role == "Arch":
        return (COLORS.PINE, f"bold {COLORS.PINE}")
    elif role == "Moderator":
        return (COLORS.PINE, f"bold {COLORS.PINE}")
    else:
        return (COLORS.TEXT, f"bold {COLORS.TEXT}")


async def handle_cli_event(
    event: dict,
    moderator,
    console: Console,
    preset: str,
    topic: str,
    output_dir: str,
) -> bool:
    """处理事件，返回是否结束

    Args:
        event: 事件字典
        moderator: DebateModerator 实例
        console: Rich Console
        preset: 预设名称
        topic: 议题
        output_dir: 输出目录

    Returns:
        是否结束流程
    """
    event_type = event.get("type", "")

    if event_type == "phase_start":
        phase = event.get("phase", "")
        console.print()
        print_panel(
            f"进入 {phase} 阶段",
            title="阶段切换",
            border_color=COLORS.IRIS,
        )

    elif event_type == "tool_call":
        # Tool 调用 - 用户输入
        tool = event.get("tool", "")
        if tool == "ask_user":
            question = event.get("question", "")
            options = event.get("options", [])
            allow_custom = event.get("allow_custom", True)

            console.print()
            console.print(f"[{COLORS.PINE}]● Moderator 询问:[/{COLORS.PINE}] [{COLORS.TEXT}]{question}[/{COLORS.TEXT}]")

            if options:
                for i, opt in enumerate(options):
                    console.print(f"  [{COLORS.SUBTLE}]{i + 1}.[/{COLORS.SUBTLE}] [{COLORS.TEXT}]{opt}[/{COLORS.TEXT}]")
                if allow_custom:
                    console.print(f"  [{COLORS.SUBTLE}]0.[/{COLORS.SUBTLE}] [{COLORS.MUTED}]自定义回答[/{COLORS.MUTED}]")

            # 用户输入
            console.print(f"[{COLORS.IRIS}]你的回答:[/{COLORS.IRIS}]", end=" ")
            user_answer = await asyncio.to_thread(input)

            # 如果选择了选项编号，转换为选项内容
            selected_option = -1
            if options and user_answer.isdigit():
                idx = int(user_answer) - 1
                if 0 <= idx < len(options):
                    user_answer = options[idx]
                    selected_option = idx

            # 提交回答到 Moderator
            moderator.submit_user_answer(user_answer, selected_option)

            # 继续澄清阶段
            async for next_event in moderator.resume_clarification():
                should_end = await handle_cli_event(next_event, moderator, console, preset, topic, output_dir)
                if should_end:
                    return True

    elif event_type == "moderator_message":
        content = event.get("content", "")
        console.print()
        console.print(f"[{COLORS.IRIS}]● Moderator:[/{COLORS.IRIS}] [{COLORS.TEXT}]{content}[/{COLORS.TEXT}]")

    elif event_type == "clarification_done":
        prd_base = event.get("prd_base", "")
        rounds = event.get("rounds", 0)
        console.print()
        status_success(f"澄清完成，共 {rounds} 轮问答")
        console.print()
        console.print(f"[{COLORS.IRIS}]PRD 基础版:[/{COLORS.IRIS}]")
        console.print(Markdown(prd_base), style=COLORS.TEXT)
        console.print()

    elif event_type == "token":
        delta = event.get("delta", "")
        role = event.get("role", "")
        token_color, _ = _get_role_colors(role)
        if token_color:
            console.print(f"[{token_color}]{delta}[/{token_color}]", end="")
        else:
            console.print(delta, end="")

    elif event_type == "message_complete":
        console.print()
        console.print(f"[{COLORS.SUBTLE}]✓ 完成[/{COLORS.SUBTLE}]")
        console.print(f"[{COLORS.MUTED}]" + "─" * 40 + f"[/{COLORS.MUTED}]")

    elif event_type == "moderator":
        content = event.get("content", "")
        console.print()
        console.print(f"[{COLORS.PINE}]● Moderator:[/{COLORS.PINE}] [{COLORS.TEXT}]{content}[/{COLORS.TEXT}]")

    elif event_type == "debate_complete":
        console.print()
        status_success(f"辩论完成，共 {event.get('rounds', 0)} 轮")
        print_kv("结束原因", event.get("reason", ""), WARNING)

        console.print()
        console.print(f"[{COLORS.IRIS}]最终 PRD:[/{COLORS.IRIS}]")
        console.print(Markdown(event.get("prd", "")), style=COLORS.TEXT)

        # 保存 PRD
        generator = PRDGenerator(output_dir=output_dir)
        filepath = generator.save_string(event.get("prd", ""), preset, topic)
        status_success(f"PRD 已保存: {filepath}")
        return True

    elif event_type == "error":
        status_error(event.get("message", "未知错误"))
        return True

    return False