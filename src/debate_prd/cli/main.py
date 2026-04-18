"""命令行入口 - 简洁交互模式"""

import argparse
import asyncio
import sys
import os
import signal

from rich.console import Console
from rich.text import Text
from rich.style import Style
from rich.table import Table

from ..config.presets import list_presets, get_preset, DEBATER_PRESETS
from ..config.settings import Settings, LLMConfig
from ..output.prd_generator import PRDGenerator
from .formatting import (
    status_success,
    status_error,
    status_info,
    print_brand_header,
    phase_separator,
    print_header,
)
from .theme import COLORS, PRIMARY, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY

console = Console()

# 全局退出标志
_shutdown_requested = False


def _signal_handler(signum, frame):
    """信号处理器 - Ctrl+C"""
    global _shutdown_requested
    _shutdown_requested = True
    console.print()
    console.print(f"[{COLORS.GOLD}]⚠ 收到退出信号[/{COLORS.GOLD}]")
    sys.exit(0)


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        prog="debate-prd",
        description="辩论式 PRD 生成系统 - 两个 AI Agent 通过辩论产出高质量产品需求文档",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  debate-prd                        # 交互模式，逐步选择预设和输入议题
  debate-prd --topic "用户认证系统" # 直接指定议题，仍需选择预设
  debate-prd --preset 1 --topic "用户认证系统"  # 完全参数化启动
  debate-prd --info                # 查看系统简介
  debate-prd --list-presets        # 列出所有预设角色

环境变量:
  OPENAI_API_KEY   - API Key (必需)
  OPENAI_BASE_URL  - API Base URL (默认: https://api.openai.com/v1)
  OPENAI_MODEL     - 模型名称 (默认: gpt-4o-mini)

更多信息请访问: https://github.com/zewang/agents-debate
        """,
    )

    parser.add_argument("--api-key", type=str, default=os.environ.get("OPENAI_API_KEY", ""))
    parser.add_argument("--base-url", type=str, default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"))
    parser.add_argument("--model", type=str, default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"))
    parser.add_argument("--max-rounds", type=int, default=6, help="辩论最大轮数 (默认: 6)")
    parser.add_argument("--preset", type=str, default=None, help="预设编号(1-3)或名称(pm_vs_dev等)")
    parser.add_argument("--topic", type=str, default=None, help="辩论议题")
    parser.add_argument("--output-dir", type=str, default="./output", help="PRD 输出目录")
    parser.add_argument("--info", action="store_true", help="显示系统简介")
    parser.add_argument("--list-presets", action="store_true", help="列出所有预设角色")

    return parser.parse_args()


def main():
    """命令行主入口"""
    signal.signal(signal.SIGINT, _signal_handler)

    args = parse_args()

    # --info: 显示系统简介
    if args.info:
        _show_info()
        return

    # --list-presets: 列出预设
    if args.list_presets:
        _show_presets_table()
        return

    # 检查 API Key
    if not args.api_key:
        console.print()
        status_error("未提供 API Key")
        console.print(f"[{TEXT_SECONDARY}]请设置环境变量 OPENAI_API_KEY 或使用 --api-key 参数[/{TEXT_SECONDARY}]")
        console.print()
        sys.exit(1)

    # 交互式选择预设
    preset = _select_preset(args.preset)

    # 交互式输入议题
    topic = _input_topic(args.topic)

    # 显示启动信息
    console.print()
    print_brand_header(args.model, preset)
    console.print(f"[{PRIMARY}]议题: {topic}[/{PRIMARY}]")
    console.print(f"[{TEXT_MUTED}]预设: {preset} | 最大轮数: {args.max_rounds}[/{TEXT_MUTED}]")
    console.print(f"[{TEXT_MUTED}]按 Ctrl+C 可随时退出[/{TEXT_MUTED}]")
    console.print()

    # 启动辩论
    llm_config = LLMConfig(api_key=args.api_key, base_url=args.base_url, model=args.model)
    asyncio.run(run_debate(llm_config, preset, topic, args.max_rounds, args.output_dir))


def _show_info():
    """显示系统简介"""
    console.print()
    print_brand_header()

    info_text = """
辩论式 PRD 生成系统

核心理念:
两个 AI Agent 持不同立场进行辩论，通过观点碰撞和共识达成，
产出更全面、更深思熟虑的产品需求文档。

工作流程:
1. 澄清阶段 - Moderator 通过问答收集需求细节
2. PRD 基础版 - 生成初始 PRD 概要
3. 辩论阶段 - PM/Dev 等角色进行自由辩论
4. 共识检测 - 自动检测共识达成或僵局
5. 用户干预 - 关键决策点或僵局时询问用户
6. PRD 生成 - 综合辩论结果生成最终文档

预设角色:
• pm_vs_dev - 产品需求 vs 技术可行性
• business_vs_security - 业务增长 vs 安全合规
• ux_vs_architecture - 用户体验 vs 系统架构

输出标记:
Agent 使用特殊标记表达观点:
• [AGREE:内容] - 完全认同
• [PARTIAL_AGREE:内容] - 部分认同
• [DISAGREE:内容] - 明确分歧
• [PRD_ITEM] 功能描述 - PRD 条目建议

快速开始:
  debate-prd --topic "你的议题"

更多信息: https://github.com/zewang/agents-debate
"""
    console.print(f"[{TEXT_PRIMARY}]{info_text}[/{TEXT_PRIMARY}]")
    console.print()


def _show_presets_table():
    """显示预设角色表格"""
    console.print()
    print_header("预设角色列表")

    table = Table(show_header=True, header_style=Style(color=PRIMARY, bold=True))
    table.add_column("编号", style=Style(color=COLORS.PINE))
    table.add_column("名称", style=Style(color=PRIMARY))
    table.add_column("角色", style=Style(color=TEXT_PRIMARY))
    table.add_column("描述", style=Style(color=TEXT_SECONDARY))

    presets = list_presets()
    for i, name in enumerate(presets, 1):
        preset_config = get_preset(name)
        role1 = preset_config["debater1"]["role"]
        role2 = preset_config["debater2"]["role"]
        desc = preset_config["description"]
        table.add_row(str(i), name, f"{role1} vs {role2}", desc)

    console.print(table)
    console.print()


def _select_preset(preset_arg: str | None) -> str:
    """交互式选择预设

    Args:
        preset_arg: 命令行传入的预设参数（编号或名称）

    Returns:
        预设名称
    """
    presets = list_presets()

    # 如果命令行已提供
    if preset_arg:
        # 数字编号
        if preset_arg.isdigit():
            idx = int(preset_arg)
            if 1 <= idx <= len(presets):
                return presets[idx - 1]
            else:
                status_error(f"预设编号无效: {preset_arg}")
                console.print(f"[{TEXT_SECONDARY}]可选编号: 1-{len(presets)}[/{TEXT_SECONDARY}]")
                sys.exit(1)
        # 直接名称
        elif preset_arg in presets:
            return preset_arg
        else:
            status_error(f"预设名称无效: {preset_arg}")
            console.print(f"[{TEXT_SECONDARY}]可选: {', '.join(presets)}[/{TEXT_SECONDARY}]")
            sys.exit(1)

    # 交互选择
    console.print()
    print_header("选择预设角色")

    table = Table(show_header=True, header_style=Style(color=PRIMARY, bold=True))
    table.add_column("编号", style=Style(color=COLORS.PINE), width=6)
    table.add_column("角色", style=Style(color=TEXT_PRIMARY), width=20)
    table.add_column("描述", style=Style(color=TEXT_SECONDARY))

    for i, name in enumerate(presets, 1):
        preset_config = get_preset(name)
        role1 = preset_config["debater1"]["role"]
        role2 = preset_config["debater2"]["role"]
        desc = preset_config["description"]
        table.add_row(str(i), f"{role1} vs {role2}", desc)

    console.print(table)
    console.print()

    while True:
        prompt = Text()
        prompt.append("请选择预设编号", style=Style(color=PRIMARY))
        prompt.append(" [1-3]", style=Style(color=TEXT_MUTED))
        prompt.append("> ", style=Style(color=COLORS.ROSE))
        console.print(prompt, end=" ")

        try:
            choice = input().strip()
        except EOFError:
            console.print()
            status_error("输入中断")
            sys.exit(1)

        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(presets):
                selected = presets[idx - 1]
                preset_config = get_preset(selected)
                status_success(f"已选择: {preset_config['debater1']['role']} vs {preset_config['debater2']['role']}")
                return selected

        status_error(f"请输入有效编号: 1-{len(presets)}")


def _input_topic(topic_arg: str | None) -> str:
    """交互式输入议题

    Args:
        topic_arg: 命令行传入的议题

    Returns:
        辩论议题
    """
    if topic_arg:
        status_success(f"议题: {topic_arg}")
        return topic_arg

    console.print()
    print_header("输入辩论议题")

    while True:
        prompt = Text()
        prompt.append("请输入议题", style=Style(color=PRIMARY))
        prompt.append("> ", style=Style(color=COLORS.ROSE))
        console.print(prompt, end=" ")

        try:
            topic = input().strip()
        except EOFError:
            console.print()
            status_error("输入中断")
            sys.exit(1)

        if topic:
            status_success(f"议题: {topic}")
            return topic

        status_error("议题不能为空，请重新输入")


async def run_debate(
    llm_config: LLMConfig, preset: str, topic: str, max_rounds: int, output_dir: str
):
    """运行辩论"""
    console.print()
    console.print(f"[{PRIMARY}]议题: {topic}[/{PRIMARY}]")
    console.print(f"[{TEXT_MUTED}]" + "━" * 40 + f"[/{TEXT_MUTED}]")
    console.print()

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
                phase_separator(event.get("phase", ""))

            elif event_type == "sub_phase":
                sub_phase = event.get("phase", "")
                note = event.get("note", "")
                if sub_phase == "publish_view":
                    console.print(f"[{COLORS.GOLD}]◆ 双方并发发表看法{f'（{note}）' if note else ''}[/{COLORS.GOLD}]")
                elif sub_phase == "free_debate":
                    console.print(f"[{COLORS.GOLD}]◆ 进入自由辩论[/{COLORS.GOLD}]")

            elif event_type == "ask":
                result = await _clarification_loop(
                    moderator, event, preset, topic, output_dir, current_role_state
                )
                if result == "done":
                    return

            elif event_type == "prd_generated":
                console.print()
                status_success("PRD基础版生成完成")

            elif event_type == "clarification_done":
                console.print()
                status_success("澄清阶段完成")
                console.print(f"[{TEXT_MUTED}]" + "━" * 40 + f"[/{TEXT_MUTED}]")

            elif event_type == "debate_complete":
                _show_complete(event, preset, topic, output_dir)
                return

            elif event_type == "stalemate_question":
                await _handle_stalemate(event, moderator, preset, topic, output_dir, current_role_state)
                return

            elif event_type == "critical_decision_question":
                await _handle_critical_decision(event, moderator, preset, topic, output_dir, current_role_state)
                return

            elif event_type == "intervention_applied":
                console.print()
                console.print(f"[{COLORS.PINE}]✓ 用户决策已注入：{event.get('answer', '')}[/{COLORS.PINE}]")

            elif event_type == "token":
                _print_token(event, current_role_state, console)

            elif event_type == "message_complete":
                _print_complete(console)

            elif event_type == "moderator":
                console.print()
                text = Text()
                text.append("● ", style=Style(color=COLORS.PINE))
                text.append("Moderator:", style=Style(color=COLORS.PINE, bold=True))
                text.append(f" {event.get('content', '')}", style=Style(color=TEXT_PRIMARY))
                console.print(text)

            elif event_type == "moderator_record":
                _print_moderator_record(event, console)

            elif event_type == "error":
                status_error(event.get("message", "错误"))
                return

    except KeyboardInterrupt:
        _handle_graceful_exit(moderator, preset, topic, output_dir)


async def _clarification_loop(
    moderator, first_event, preset, topic, output_dir, current_role_state
):
    """澄清阶段问答循环"""
    event = first_event

    while True:
        if _shutdown_requested:
            _handle_graceful_exit(moderator, preset, topic, output_dir)
            return "done"

        question = event.get("question", "")
        console.print()
        text = Text()
        text.append("● ", style=Style(color=COLORS.PINE))
        text.append("Moderator:", style=Style(color=COLORS.PINE, bold=True))
        text.append(f" {question}", style=Style(color=TEXT_PRIMARY))
        console.print(text)

        answer_prompt = Text()
        answer_prompt.append("你的回答", style=Style(color=PRIMARY))
        answer_prompt.append("> ", style=Style(color=COLORS.ROSE))
        console.print(answer_prompt, end=" ")
        answer = await asyncio.to_thread(input)
        moderator.submit_user_answer(answer)

        found_ask = False
        async for e in moderator.resume_clarification():
            t = e.get("type", "")

            if t == "ask":
                event = e
                found_ask = True
                break

            elif t == "prd_generated":
                console.print()
                status_success("PRD基础版生成完成")

            elif t == "clarification_done":
                console.print()
                status_success("澄清阶段完成")
                console.print(f"[{TEXT_MUTED}]" + "━" * 40 + f"[/{TEXT_MUTED}]")
                # 继续处理后续辩论事件，不立即返回

            elif t == "phase_start":
                phase = e.get("phase", "")
                # 只显示 debate 阶段分隔符，跳过 prd_generation（已在流式输出前处理）
                if phase == "debate":
                    phase_separator(phase)

            elif t == "sub_phase":
                sub_phase = e.get("phase", "")
                note = e.get("note", "")
                if sub_phase == "publish_view":
                    console.print(f"[{COLORS.GOLD}]◆ 双方并发发表看法{f'（{note}）' if note else ''}[/{COLORS.GOLD}]")

            elif t == "debate_complete":
                _show_complete(e, preset, topic, output_dir)
                return "done"

            elif t == "token":
                _print_token(e, current_role_state, console)

            elif t == "message_complete":
                _print_complete(console)

            elif t == "moderator":
                console.print()
                text = Text()
                text.append("● ", style=Style(color=COLORS.PINE))
                text.append("Moderator:", style=Style(color=COLORS.PINE, bold=True))
                text.append(f" {e.get('content', '')}", style=Style(color=TEXT_PRIMARY))
                console.print(text)

            elif t == "moderator_record":
                _print_moderator_record(e, console)

            elif t == "stalemate_question":
                await _handle_stalemate(e, moderator, preset, topic, output_dir, current_role_state)
                return "done"

            elif t == "critical_decision_question":
                await _handle_critical_decision(e, moderator, preset, topic, output_dir, current_role_state)
                return "done"

            elif t == "error":
                status_error(e.get("message", "错误"))
                return "done"

        if found_ask:
            continue

        return "done"


def _handle_graceful_exit(moderator, preset: str, topic: str, output_dir: str):
    """处理优雅退出"""
    console.print()
    console.print(f"[{COLORS.GOLD}]⚠ 用户中断辩论[/{COLORS.GOLD}]")

    if moderator and hasattr(moderator, "_prd_base") and moderator._prd_base:
        console.print(f"[{TEXT_PRIMARY}]正在保存当前进度...[/{TEXT_PRIMARY}]")
        generator = PRDGenerator(output_dir=output_dir)
        generator.save_string(moderator._prd_base, preset, topic + "_partial")
        status_success("进度已保存")

    console.print()
    console.print(f"[{TEXT_SECONDARY}]再见！下次继续辩论吧。[/{TEXT_SECONDARY}]")


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
    console.file.flush()


def _print_complete(console: Console):
    """打印完成标记"""
    console.print()
    console.print(f"[{COLORS.PINE}]✓ 完成[/{COLORS.PINE}]")
    console.print(f"[{TEXT_MUTED}]" + "━" * 40 + f"[/{TEXT_MUTED}]")


def _get_role_colors(role: str) -> tuple[str, str]:
    """获取角色颜色"""
    if role == "PM":
        return (COLORS.IRIS, f"bold {COLORS.IRIS}")
    elif role == "Dev":
        return (COLORS.FOAM, f"bold {COLORS.FOAM}")
    elif role == "Moderator":
        return (COLORS.PINE, f"bold {COLORS.PINE}")
    else:
        return (COLORS.ROSE, f"bold {COLORS.ROSE}")


async def _handle_stalemate(event, moderator, preset, topic, output_dir, current_role_state):
    """处理僵局询问"""
    console.print()
    console.print(f"[{COLORS.ROSE}]━━ 僵局检测 ━━[/{COLORS.ROSE}]")
    console.print(f"[{TEXT_PRIMARY}]{event.get('question', '')}[/{TEXT_PRIMARY}]")
    if event.get("disagreements"):
        console.print(f"[{TEXT_MUTED}]分歧点：[/{TEXT_MUTED}]")
        console.print(event.get("disagreements", ""))

    answer_prompt = Text()
    answer_prompt.append("您的看法", style=Style(color=PRIMARY, bold=True))
    answer_prompt.append("> ", style=Style(color=COLORS.ROSE))
    console.print(answer_prompt, end=" ")
    answer = await asyncio.to_thread(input)

    moderator.submit_intervention(answer)
    async for resume_event in moderator.resume_debate():
        resume_type = resume_event.get("type", "")
        if resume_type == "intervention_applied":
            console.print()
            console.print(f"[{COLORS.PINE}]✓ 用户决策已注入：{resume_event.get('answer', '')}[/{COLORS.PINE}]")
        elif resume_type == "debate_complete":
            _show_complete(resume_event, preset, topic, output_dir)
            return
        elif resume_type == "token":
            _print_token(resume_event, current_role_state, console)
        elif resume_type == "message_complete":
            _print_complete(console)
        elif resume_type == "moderator_record":
            _print_moderator_record(resume_event, console)
        elif resume_type == "stalemate_question":
            await _handle_stalemate(resume_event, moderator, preset, topic, output_dir, current_role_state)
            return
        elif resume_type == "critical_decision_question":
            await _handle_critical_decision(resume_event, moderator, preset, topic, output_dir, current_role_state)
            return


async def _handle_critical_decision(event, moderator, preset, topic, output_dir, current_role_state):
    """处理关键决策询问"""
    console.print()
    console.print(f"[{COLORS.GOLD}]━━ 关键决策点 ━━[/{COLORS.GOLD}]")
    console.print(f"[{TEXT_PRIMARY}]{event.get('question', '')}[/{TEXT_PRIMARY}]")

    options = event.get("options", [])
    if options:
        for i, opt in enumerate(options):
            console.print(f"[{TEXT_MUTED}]  [{i+1}] {opt}[/{TEXT_MUTED}]")
        console.print(f"[{TEXT_MUTED}]  [其他] 输入自定义回答[/{TEXT_MUTED}]")
        console.print(f"[{TEXT_MUTED}]  [跳过] 按 Enter 跳过[/{TEXT_MUTED}]")

    answer_prompt = Text()
    answer_prompt.append("您的回答", style=Style(color=PRIMARY))
    answer_prompt.append("> ", style=Style(color=COLORS.ROSE))
    console.print(answer_prompt, end=" ")
    answer = await asyncio.to_thread(input)

    if answer.strip():
        if options and answer.isdigit():
            idx = int(answer) - 1
            if 0 <= idx < len(options):
                answer = options[idx]

        moderator.submit_intervention(answer, event.get("category"))
        async for resume_event in moderator.resume_debate():
            resume_type = resume_event.get("type", "")
            if resume_type == "intervention_applied":
                console.print()
                console.print(f"[{COLORS.PINE}]✓ 用户决策已注入：{resume_event.get('answer', '')}[/{COLORS.PINE}]")
            elif resume_type == "debate_complete":
                _show_complete(resume_event, preset, topic, output_dir)
                return
            elif resume_type == "token":
                _print_token(resume_event, current_role_state, console)
            elif resume_type == "message_complete":
                _print_complete(console)
            elif resume_type == "moderator_record":
                _print_moderator_record(resume_event, console)
            elif resume_type == "stalemate_question":
                await _handle_stalemate(resume_event, moderator, preset, topic, output_dir, current_role_state)
                return
            elif resume_type == "critical_decision_question":
                await _handle_critical_decision(resume_event, moderator, preset, topic, output_dir, current_role_state)
                return
    else:
        console.print(f"[{TEXT_MUTED}]已跳过[/{TEXT_MUTED}]")


def _print_moderator_record(event, console):
    """打印 Moderator 记录"""
    console.print()
    console.print(f"[{TEXT_SECONDARY}]━━ Moderator 记录 ━━[/{TEXT_SECONDARY}]")
    for line in event.get("content", "").split("\n"):
        if line.startswith("  ✓"):
            console.print(f"[{COLORS.PINE}]{line}[/{COLORS.PINE}]")
        elif line.startswith("  ◐"):
            console.print(f"[{COLORS.GOLD}]{line}[/{COLORS.GOLD}]")
        elif line.startswith("  ✗"):
            console.print(f"[{COLORS.ROSE}]{line}[/{COLORS.ROSE}]")
        elif line.startswith("  📊"):
            console.print(f"[{COLORS.IRIS}]{line}[/{COLORS.IRIS}]")
        else:
            console.print(f"[{TEXT_PRIMARY}]{line}[/{TEXT_PRIMARY}]")


def _show_complete(event: dict, preset: str, topic: str, output_dir: str):
    """显示完成"""
    console.print()
    status_success(f"辩论完成，共 {event.get('rounds', 0)} 轮")

    reason = event.get("reason", "")
    if reason:
        console.print(f"[{TEXT_MUTED}]结束原因: {reason}[/{TEXT_MUTED}]")

    prd = event.get("prd", "")
    if prd:
        console.print()
        from rich.markdown import Markdown
        console.print(Markdown(prd), style=TEXT_PRIMARY)

    generator = PRDGenerator(output_dir=output_dir)
    generator.save_string(prd, preset, topic)
    console.print()
    status_success("PRD 已保存")


if __name__ == "__main__":
    main()