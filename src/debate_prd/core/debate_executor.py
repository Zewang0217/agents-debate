"""辩论执行器 - 自由辩论循环逻辑

从 debate_loop.py 拆分，负责辩论执行：
- 并发发表看法
- 自由辩论循环
- 用户介入处理
- 深度分析触发

关键改进：
- 使用 Guard Clause 减少嵌套（不超过 3 层）
- 函数长度不超过 50 行
- 统一使用 logging 替代 print
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from .logger import get_logger

if TYPE_CHECKING:
    from .debate_loop import DebateModerator, DebateState

logger = get_logger("executor")


class DebateExecutor:
    """辩论执行器 - 管理自由辩论循环"""

    RECORD_INTERVAL = 2
    DEEP_ANALYSIS_INTERVAL = 2
    STALEMATE_THRESHOLD = 2
    MIN_ROUNDS_BEFORE_TERMINATION = 4

    def __init__(self, moderator: "DebateModerator"):
        self._moderator = moderator
        self._state: "DebateState" = moderator._debate_state
        self._last_record_round = 0
        self._last_deep_analysis_round = 0
        self._recent_messages: list[str] = []

    async def run_free_debate(self, topic: str, prd_base: str):
        """自由辩论主入口 - 合并原有的超长函数

        流程：
        1. 并发发表看法
        2. 第一轮分析
        3. 自由辩论循环

        Args:
            topic: 辩论议题
            prd_base: PRD 基础版
        """
        logger.info(f"自由辩论开始 topic={topic[:50]}")

        yield {"type": "sub_phase", "phase": "publish_view", "note": "依次展示"}

        async for event in self._publish_initial_views(topic, prd_base):
            yield event

        async for event in self._analyze_first_round():
            yield event

        yield {"type": "sub_phase", "phase": "free_debate"}

        async for event in self._run_free_debate_loop(topic, prd_base):
            yield event

        logger.info(f"自由辩论结束 rounds={self._state.round_num}")

    async def _publish_initial_views(self, topic: str, prd_base: str):
        """并发发表看法（依次展示）"""
        pm_events: list[dict] = []
        dev_events: list[dict] = []

        async def collect_pm():
            async for event in self._moderator.debater1.publish_view(topic, prd_base):
                pm_events.append(event)

        async def collect_dev():
            async for event in self._moderator.debater2.publish_view(topic, prd_base):
                dev_events.append(event)

        await asyncio.gather(collect_pm(), collect_dev())

        for event in pm_events:
            yield event
            if event.get("type") == "message_complete":
                self._handle_message_complete(event, "pm")

        for event in dev_events:
            yield event
            if event.get("type") == "message_complete":
                self._handle_message_complete(event, "dev")

        yield self._moderator._generate_moderator_record("并发发表看法完成")
        logger.info(
            f"并发发表完成 pm_events={len(pm_events)} dev_events={len(dev_events)}"
        )

    def _handle_message_complete(self, event: dict, role: str):
        """处理消息完成事件"""
        content = event.get("content", "")
        self._moderator._extract_prd_items(content)
        self._state.round_num += 1
        self._moderator._extract_points(content, self._moderator._topic)
        self._recent_messages.append(content)

    async def _analyze_first_round(self):
        """第一轮中控 LLM 分析"""
        pm_content = self._get_last_pm_content()
        dev_content = self._get_last_dev_content()

        if not pm_content or not dev_content or not self._moderator._llm_client:
            return

        result = await self._moderator._analyze_first_round(pm_content, dev_content)
        if result:
            yield self._moderator._generate_round_summary(result)
            logger.info(
                f"第一轮分析完成 consensus_count={len(self._state.locked_consensus)}"
            )

    def _get_last_pm_content(self) -> str:
        """获取 PM 最后发言内容"""
        return self._recent_messages[-2] if len(self._recent_messages) >= 2 else ""

    def _get_last_dev_content(self) -> str:
        """获取 Dev 最后发言内容"""
        return self._recent_messages[-1] if len(self._recent_messages) >= 1 else ""

    async def _run_free_debate_loop(self, topic: str, prd_base: str):
        """自由辩论循环 - 使用 Guard Clause 减少嵌套"""
        self._last_record_round = self._state.round_num
        self._last_deep_analysis_round = self._state.round_num

        while not self._state.terminated:
            if self._check_should_exit():
                return

            if self._has_pending_intervention():
                async for event in self._inject_intervention():
                    yield event
                continue

            if self._should_ask_stalemate():
                yield self._generate_stalemate_question()
                return

            if self._check_termination():
                break

            async for event in self._run_single_round(topic, prd_base):
                yield event

    def _check_should_exit(self) -> bool:
        """检查是否应该退出循环"""
        return (
            self._state.terminated
            and self._state.stalemate_count < self.STALEMATE_THRESHOLD
        )

    def _has_pending_intervention(self) -> bool:
        """检查是否有待处理的用户介入"""
        return (
            hasattr(self._moderator, "_pending_user_intervention")
            and self._moderator._pending_user_intervention
        )

    def _should_ask_stalemate(self) -> bool:
        """检查是否应该询问僵局"""
        if (
            self._state.stalemate_count >= self.STALEMATE_THRESHOLD
            and not self._state.terminated
        ):
            self._state.terminated = True
            self._state.termination_reason = "辩论僵局-等待用户介入"
            return True
        return False

    async def _inject_intervention(self):
        """注入用户介入"""
        intervention = self._moderator._pending_user_intervention
        self._moderator._pending_user_intervention = None

        from .messaging.mailbox import send_to_agent

        msg = f"[Moderator 补充信息]\n用户决策：{intervention['answer']}\n请基于此约束继续辩论。"
        await send_to_agent("moderator", "debater1", msg)
        await send_to_agent("moderator", "debater2", msg)

        yield {"type": "intervention_applied", "answer": intervention["answer"]}
        logger.info(f"用户决策已注入 answer={intervention['answer'][:50]}")

    def _check_termination(self) -> bool:
        """检查终止条件"""
        return self._moderator._check_termination()

    def _generate_stalemate_question(self) -> dict:
        """生成僵局询问"""
        logger.info(f"僵局检测 rounds={self._state.round_num}")
        return self._moderator._generate_stalemate_question()

    async def _run_single_round(self, topic: str, prd_base: str):
        """执行单轮辩论"""
        moderator_sync = self._moderator._build_moderator_sync()
        responded = False
        pm_content = ""
        dev_content = ""

        for debater in [self._moderator.debater1, self._moderator.debater2]:
            messages = await debater._mailbox.get_messages()
            if not messages:
                continue

            opponent_msg = messages[-1].content
            full_content = ""

            async for event in debater.respond_stream(
                topic, opponent_msg, prd_base, moderator_sync
            ):
                yield event
                if event.get("type") == "message_complete":
                    full_content = event["content"]

            if full_content:
                self._handle_debater_response(full_content, debater)
                responded = True

                if debater == self._moderator.debater1:
                    pm_content = full_content
                else:
                    dev_content = full_content

        if not responded:
            await asyncio.sleep(0.5)
            return

        await self._post_round_analysis(pm_content, dev_content)

        async for event in self._yield_round_events():
            yield event

    def _handle_debater_response(self, content: str, debater):
        """处理辩手响应"""
        self._moderator._extract_prd_items(content)
        self._state.round_num += 1
        self._moderator._extract_points(content)
        self._recent_messages.append(content)

        quick_result = self._moderator._quick_analyze_round("", content)
        if quick_result.get("progress_detected"):
            self._state.stalemate_count = 0
        else:
            self._state.stalemate_count += 1

        self._moderator._process_new_markers(quick_result)

        for d in self._state.active_disagreements:
            if not d.resolved:
                d.attempts += 1

    async def _post_round_analysis(self, pm_content: str, dev_content: str):
        """轮后分析"""
        if pm_content or dev_content:
            self._state.debate_summary.append(
                {
                    "round": self._state.round_num,
                    "pm_key_points": pm_content[:300],
                    "dev_key_points": dev_content[:300],
                }
            )

    async def _yield_round_events(self):
        """输出轮次事件"""
        if self._state.round_num - self._last_record_round >= self.RECORD_INTERVAL:
            yield self._moderator._generate_moderator_record("自由辩论进展")
            self._last_record_round = self._state.round_num

        if (
            self._state.round_num - self._last_deep_analysis_round
            >= self.DEEP_ANALYSIS_INTERVAL
        ):
            await self._moderator._deep_analyze_rounds(
                recent_rounds=self.DEEP_ANALYSIS_INTERVAL
            )
            self._last_deep_analysis_round = self._state.round_num

        critical = self._moderator._detect_critical_decision(self._recent_messages)
        if critical:
            yield {
                "type": "critical_decision_question",
                "category": critical["category"],
                "keyword": critical["keyword"],
                "question": critical["question"],
                "options": critical["options"],
                "allow_skip": True,
            }
            logger.info(f"关键决策检测 category={critical['category']}")

    async def continue_free_debate(self):
        """继续自由辩论（中断恢复）"""
        self._last_record_round = self._state.round_num
        self._last_deep_analysis_round = self._state.round_num

        async for event in self._run_free_debate_loop(
            self._moderator._topic, self._moderator._prd_base
        ):
            yield event
