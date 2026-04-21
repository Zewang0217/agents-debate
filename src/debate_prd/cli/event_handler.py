"""事件处理器 - 辩论事件流处理

从 main.py 拆分，负责：
- 事件分发和渲染
- 用户交互处理
- 澄清阶段循环
- 僵局/关键决策处理

关键改进：
- 函数长度不超过 50 行
- 使用 Guard Clause 减少嵌套
- 统一事件处理入口
"""

import asyncio
from typing import TYPE_CHECKING

from rich.console import Console
from rich.text import Text
from rich.style import Style

from .theme import COLORS, PRIMARY, TEXT_MUTED, TEXT_PRIMARY, TEXT_SECONDARY
from .formatting import (
    phase_separator,
    format_round_summary,
    status_success,
    status_error,
)

if TYPE_CHECKING:
    from ..core.debate_loop import DebateModerator

console = Console()


class EventHandler:
    """事件处理器 - 管理辩论事件流"""

    def __init__(
        self, moderator: "DebateModerator", preset: str, topic: str, output_dir: str
    ):
        self._moderator = moderator
        self._preset = preset
        self._topic = topic
        self._output_dir = output_dir
        self._current_role = ""

    async def handle_event(self, event: dict) -> str | None:
        """统一事件处理入口

        Returns:
            返回 "done" 表示辩论结束，None 表示继续
        """
        event_type = event.get("type", "")

        handlers = {
            "phase_start": self._handle_phase_start,
            "sub_phase": self._handle_sub_phase,
            "ask": self._handle_ask,
            "prd_generated": self._handle_prd_generated,
            "clarification_done": self._handle_clarification_done,
            "debate_complete": self._handle_debate_complete,
            "stalemate_question": self._handle_stalemate_question,
            "stalemate_intervention": self._handle_stalemate_intervention,
            "critical_decision_intervention": self._handle_critical_intervention,
            "critical_decision_question": self._handle_critical_decision,
            "intervention_applied": self._handle_intervention_applied,
            "token": self._handle_token,
            "message_complete": self._handle_message_complete,
            "moderator": self._handle_moderator,
            "moderator_record": self._handle_moderator_record,
            "round_summary": self._handle_round_summary,
            "error": self._handle_error,
        }

        handler = handlers.get(event_type)
        if handler:
            return await handler(event)

        return None

    async def _handle_phase_start(self, event: dict) -> None:
        """处理阶段开始"""
        phase_separator(event.get("phase", ""))

    async def _handle_sub_phase(self, event: dict) -> None:
        """处理子阶段"""
        sub_phase = event.get("phase", "")
        note = event.get("note", "")

        if sub_phase == "publish_view":
            console.print(
                f"[{COLORS.GOLD}]◆ 双方并发发表看法{f'（{note}）' if note else ''}[/{COLORS.GOLD}]"
            )
        elif sub_phase == "free_debate":
            console.print(f"[{COLORS.GOLD}]◆ 进入自由辩论[/{COLORS.GOLD}]")

    async def _handle_ask(self, event: dict) -> str | None:
        """处理澄清阶段问答"""
        return await self._run_clarification_loop(event)

    async def _handle_prd_generated(self, event: dict) -> None:
        """处理 PRD 生成"""
        console.print()
        status_success("PRD基础版生成完成")

    async def _handle_clarification_done(self, event: dict) -> None:
        """处理澄清完成"""
        console.print()
        status_success("澄清阶段完成")
        console.print(f"[{TEXT_MUTED}]" + "━" * 40 + f"[/{TEXT_MUTED}]")

    async def _handle_debate_complete(self, event: dict) -> str:
        """处理辩论完成"""
        self._show_complete(event)
        return "done"

    async def _handle_stalemate_question(self, event: dict) -> str:
        """处理僵局询问"""
        await self._handle_stalemate(event)
        return "done"

    async def _handle_stalemate_intervention(self, event: dict) -> str:
        """处理僵局干预"""
        await self._handle_stalemate_intervention_internal(event)
        return "done"

    async def _handle_critical_intervention(self, event: dict) -> str:
        """处理关键决策干预"""
        await self._handle_critical_intervention_internal(event)
        return "done"

    async def _handle_critical_decision(self, event: dict) -> str:
        """处理关键决策询问"""
        await self._handle_critical_decision_internal(event)
        return "done"

    async def _handle_intervention_applied(self, event: dict) -> None:
        """处理介入应用"""
        console.print()
        console.print(
            f"[{COLORS.PINE}]✓ 用户决策已注入：{event.get('answer', '')}[/{COLORS.PINE}]"
        )

    async def _handle_token(self, event: dict) -> None:
        """处理 token 流式输出"""
        self._print_token(event)

    async def _handle_message_complete(self, event: dict) -> None:
        """处理消息完成"""
        console.print()
        console.print(f"[{COLORS.PINE}]✓ 完成[/{COLORS.PINE}]")
        console.print(f"[{TEXT_MUTED}]" + "━" * 40 + f"[/{TEXT_MUTED}]")

    async def _handle_moderator(self, event: dict) -> None:
        """处理 Moderator 消息"""
        console.print()
        text = Text()
        text.append("● ", style=Style(color=COLORS.PINE))
        text.append("Moderator:", style=Style(color=COLORS.PINE, bold=True))
        text.append(f" {event.get('content', '')}", style=Style(color=TEXT_PRIMARY))
        console.print(text)

    async def _handle_moderator_record(self, event: dict) -> None:
        """处理 Moderator 记录"""
        self._print_moderator_record(event)

    async def _handle_round_summary(self, event: dict) -> None:
        """处理轮次总结"""
        format_round_summary(event)

    async def _handle_error(self, event: dict) -> str:
        """处理错误"""
        status_error(event.get("message", "错误"))
        return "done"

    async def _run_clarification_loop(self, first_event: dict) -> str:
        """澄清阶段问答循环"""
        event = first_event

        while True:
            question = event.get("question", "")
            self._print_moderator_question(question)

            answer = await self._get_user_input("你的回答")
            self._moderator.submit_user_answer(answer)

            found_ask = False
            async for e in self._moderator.resume_clarification():
                result = await self.handle_event(e)
                if result == "done":
                    return "done"

                if e.get("type") == "ask":
                    event = e
                    found_ask = True
                    break

            if not found_ask:
                return "done"

    def _print_moderator_question(self, question: str):
        """打印 Moderator 问题"""
        console.print()
        text = Text()
        text.append("● ", style=Style(color=COLORS.PINE))
        text.append("Moderator:", style=Style(color=COLORS.PINE, bold=True))
        text.append(f" {question}", style=Style(color=TEXT_PRIMARY))
        console.print(text)

    async def _get_user_input(self, prompt_text: str) -> str:
        """获取用户输入"""
        prompt = Text()
        prompt.append(prompt_text, style=Style(color=PRIMARY))
        prompt.append("> ", style=Style(color=COLORS.ROSE))
        console.print(prompt, end=" ")
        return await asyncio.to_thread(input)

    async def _handle_stalemate(self, event: dict):
        """处理僵局询问"""
        console.print()
        console.print(f"[{COLORS.ROSE}]━━ 僵局检测 ━━[/{COLORS.ROSE}]")
        console.print(f"[{TEXT_PRIMARY}]{event.get('question', '')}[/{TEXT_PRIMARY}]")

        if event.get("disagreements"):
            console.print(f"[{TEXT_MUTED}]分歧点：[/{TEXT_MUTED}]")
            console.print(event.get("disagreements", ""))

        answer = await self._get_user_input("您的看法")
        self._moderator.submit_intervention(answer)

        async for resume_event in self._moderator.resume_debate():
            result = await self.handle_event(resume_event)
            if result == "done":
                return

    async def _handle_stalemate_intervention_internal(self, event: dict):
        """处理僵局干预（必须回答）"""
        console.print()
        console.print(f"[{COLORS.ROSE}]━━ 僵局干预 ━━[/{COLORS.ROSE}]")
        console.print(
            f"[{TEXT_PRIMARY}]议题：{event.get('topic', '')}[/{TEXT_PRIMARY}]"
        )
        console.print(
            f"[{TEXT_SECONDARY}]PM立场：{event.get('pm_position', '')}[/{TEXT_SECONDARY}]"
        )
        console.print(
            f"[{TEXT_SECONDARY}]Dev立场：{event.get('dev_position', '')}[/{TEXT_SECONDARY}]"
        )
        console.print(
            f"[{COLORS.GOLD}]已僵持 {event.get('attempts', 0)} 轮，请给出决策[/{COLORS.GOLD}]"
        )

        self._show_options(event.get("options", []))
        answer = await self._get_user_input("您的决策")

        await self._inject_decision_and_continue(answer, event.get("topic", ""))

    async def _handle_critical_decision_internal(self, event: dict):
        """处理关键决策询问"""
        console.print()
        console.print(f"[{COLORS.GOLD}]━━ 关键决策点 ━━[/{COLORS.GOLD}]")
        console.print(f"[{TEXT_PRIMARY}]{event.get('question', '')}[/{TEXT_PRIMARY}]")

        options = event.get("options", [])
        if options:
            self._show_options_with_skip(options)

        answer = await self._get_user_input("您的回答")

        if answer.strip():
            if options and answer.isdigit():
                idx = int(answer) - 1
                if 0 <= idx < len(options):
                    answer = options[idx]

            self._moderator.submit_intervention(answer, event.get("category"))
            await self._continue_debate_after_intervention()
        else:
            console.print(f"[{TEXT_MUTED}]已跳过[/{TEXT_MUTED}]")

    async def _handle_critical_intervention_internal(self, event: dict):
        """处理关键决策干预"""
        console.print()
        console.print(f"[{COLORS.GOLD}]━━ 关键决策干预 ━━[/{COLORS.GOLD}]")
        console.print(
            f"[{TEXT_PRIMARY}]类别：{event.get('category', '')}[/{TEXT_PRIMARY}]"
        )
        console.print(
            f"[{TEXT_PRIMARY}]议题：{event.get('topic', '')}[/{TEXT_PRIMARY}]"
        )
        console.print(
            f"[{TEXT_SECONDARY}]PM立场：{event.get('pm_position', '')}[/{TEXT_SECONDARY}]"
        )
        console.print(
            f"[{TEXT_SECONDARY}]Dev立场：{event.get('dev_position', '')}[/{TEXT_SECONDARY}]"
        )

        options = event.get("options", [])
        if options:
            self._show_options_with_skip(options)

        answer = await self._get_user_input("您的决策")

        if answer.strip():
            if options and answer.isdigit():
                idx = int(answer) - 1
                if 0 <= idx < len(options):
                    answer = options[idx]

            await self._inject_decision_and_continue(answer, event.get("topic", ""))
        else:
            console.print(f"[{TEXT_MUTED}]已跳过[/{TEXT_MUTED}]")

    def _show_options(self, options: list[str]):
        """显示选项"""
        for i, opt in enumerate(options):
            console.print(f"[{TEXT_MUTED}]  [{i + 1}] {opt}[/{TEXT_MUTED}]")

    def _show_options_with_skip(self, options: list[str]):
        """显示选项（带跳过）"""
        for i, opt in enumerate(options):
            console.print(f"[{TEXT_MUTED}]  [{i + 1}] {opt}[/{TEXT_MUTED}]")
        console.print(f"[{TEXT_MUTED}]  [其他] 输入自定义回答[/{TEXT_MUTED}]")
        console.print(f"[{TEXT_MUTED}]  [跳过] 按 Enter 跳过[/{TEXT_MUTED}]")

    async def _inject_decision_and_continue(self, answer: str, topic: str):
        """注入决策并继续"""
        await self._moderator._inject_user_decision(answer, topic)

        console.print()
        console.print(f"[{COLORS.PINE}]✓ 决策已注入：{answer}[/{COLORS.PINE}]")

        async for resume_event in self._moderator.resume_debate():
            result = await self.handle_event(resume_event)
            if result == "done":
                return

    async def _continue_debate_after_intervention(self):
        """介入后继续辩论"""
        async for resume_event in self._moderator.resume_debate():
            result = await self.handle_event(resume_event)
            if result == "done":
                return

    def _print_token(self, event: dict):
        """打印 token - 流式输出"""
        delta = event.get("delta", "")
        role = event.get("role", "")
        current_role = self._current_role

        if role != current_role:
            console.print()
            tc, pc = self._get_role_colors(role)
            console.print(f"[{pc}]【{role}】[/{pc}]", end="")
            self._current_role = role

        tc, _ = self._get_role_colors(role)
        console.print(f"[{tc}]{delta}[/{tc}]", end="")
        console.file.flush()

    def _get_role_colors(self, role: str) -> tuple[str, str]:
        """获取角色颜色"""
        if role == "PM":
            return (COLORS.IRIS, f"bold {COLORS.IRIS}")
        elif role == "Dev":
            return (COLORS.FOAM, f"bold {COLORS.FOAM}")
        elif role == "Moderator":
            return (COLORS.PINE, f"bold {COLORS.PINE}")
        else:
            return (COLORS.ROSE, f"bold {COLORS.ROSE}")

    def _print_moderator_record(self, event: dict):
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

    def _show_complete(self, event: dict):
        """显示完成"""
        from ..output.prd_generator import PRDGenerator
        from rich.markdown import Markdown

        console.print()
        status_success(f"辩论完成，共 {event.get('rounds', 0)} 轮")

        reason = event.get("reason", "")
        if reason:
            console.print(f"[{TEXT_MUTED}]结束原因: {reason}[/{TEXT_MUTED}]")

        prd = event.get("prd", "")
        if prd:
            console.print()
            console.print(Markdown(prd), style=TEXT_PRIMARY)

        generator = PRDGenerator(output_dir=self._output_dir)
        generator.save_string(prd, self._preset, self._topic)
        console.print()
        status_success("PRD 已保存")
