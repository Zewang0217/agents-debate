"""辩论循环控制 - Moderator Agent驱动

完整流程：
CLARIFICATION(Agent问答) → DEBATE → INTERVENTION → SYNTHESIS → COMPLETE

Moderator作为LLM Agent，通过function calling调用ask_user Tool动态问答。

重构改进：
- 引入 DebateExecutor 执行辩论循环
- 引入 DebateAnalyzer 进行 LLM 分析
- 使用 logging 替代 print
- Guard Clause 减少嵌套
- 数据类拆分到 debate_state.py
- ClarificationModerator 拆分到 clarification_moderator.py
"""

from typing import Optional
import asyncio
import json
import re
import jieba

from .debate_state import (
    ModeratorState,
    ConsensusPoint,
    DisagreementPoint,
    PRDItem,
    ClarificationState,
    PRDQuestioningState,
    GuidanceState,
    DebateState,
)
from .debate_points import (
    update_state_from_analysis,
    find_disagreement,
    format_disagreements,
    format_consensus,
    format_disagreement,
    categorize_prd_items,
    apply_deep_analysis_result,
)
from .debate_analysis import (
    quick_analyze_round,
    detect_off_topic,
    detect_hallucinated_reference,
    extract_keywords,
    detect_critical_decision,
    get_decision_options,
)
from .clarification_moderator import ClarificationModerator
from .spawn.debater_agent import DebaterAgent, create_debater_pair
from .messaging.mailbox import get_message_router, reset_message_router
from .tools.ask_user import AskUserTool
from .tools.moderator_tools import ModeratorTools
from .logger import get_logger
from ..config.settings import Settings
from ..config.prompts import (
    MODERATOR_ANALYSIS_PROMPT,
    MODERATOR_DEEP_ANALYSIS_PROMPT,
    MODERATOR_DEEP_ANALYSIS_PROMPT_V2,
    MODERATOR_INSIGHT_PROMPT,
)
from .prd_draft import PRDWorkingDraft, PRDItemExtended

logger = get_logger("loop")


def _clean_unicode(text: str) -> str:
    """清理无效 Unicode 字符"""
    text = re.sub(r"[\ud800-\udfff]", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = text.replace("\r", "")
    return text


class DebateModerator:
    """辩论主持人 - 状态机驱动"""

    DEFAULT_PRD_QUESTIONS = [
        ("目标用户", "这个产品/功能的目标用户是谁？请描述用户画像。"),
        ("核心功能", "核心功能是什么？请列出最重要的3-5个功能点。"),
        ("解决问题", "这个产品主要解决什么问题？用户的痛点是什么？"),
        ("成功指标", "如何衡量这个功能的成功？有哪些关键指标？"),
        ("约束条件", "有什么特殊的约束或限制？（时间、预算、技术、合规）"),
    ]

    def __init__(
        self,
        debater1: DebaterAgent,
        debater2: DebaterAgent,
        llm_client=None,  # 新增：用于澄清阶段
        settings: Settings = None,
        ask_user_tool=None,
    ):
        self.debater1 = debater1
        self.debater2 = debater2
        self._llm_client = llm_client
        self.settings = settings or Settings()

        # 状态机
        self._state = ModeratorState.CLARIFICATION
        self._questioning_state = PRDQuestioningState()
        self._guidance_state = GuidanceState()
        self._debate_state = DebateState()

        # Tool机制
        self._ask_user_tool = ask_user_tool
        self._moderator_tools = ModeratorTools()  # 新增：中控主动干预工具

        # 已询问过的关键决策点（避免重复）
        self._asked_decisions: set[str] = set()

        # ClarificationModerator
        self._clarification_moderator: Optional[ClarificationModerator] = None

        # PRD内容
        self._prd_base: str = ""
        self._topic: str = ""
        self._prd_draft: Optional[PRDWorkingDraft] = None  # 新增：PRD工作草稿

        # 注册moderator邮箱
        self._mailbox = get_message_router().register_agent("moderator")

    async def _analyze_first_round(self, pm_content: str, dev_content: str) -> dict:
        """第一轮中控 LLM 分析

        Args:
            pm_content: PM 第一轮发言
            dev_content: Dev 第一轮发言

        Returns:
            分析结果字典
        """
        if not self._llm_client:
            return {}

        prompt = MODERATOR_ANALYSIS_PROMPT.format(
            prd_base=self._prd_base,
            pm_content=pm_content,
            dev_content=dev_content,
        )

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._llm_client.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            content = response.choices[0].message.content or ""
            # 提取 JSON（可能被 markdown 包裹）
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(content)

            # 更新 DebateState
            self._update_state_from_analysis(result, round_num=1)
            return result

        except Exception as e:
            logger.error(f"第一轮分析失败 error={e}")
            return {}

    def _update_state_from_analysis(self, analysis: dict, round_num: int):
        """更新辩论状态（委托到 debate_points 模块）"""
        update_state_from_analysis(self._debate_state, analysis, round_num)

    def _find_disagreement(self, topic: str) -> Optional[DisagreementPoint]:
        """查找分歧点（委托到 debate_points 模块）"""
        return find_disagreement(self._debate_state, topic)

    def _build_moderator_sync(self) -> str:
        """构建中控同步信息给 Debater（完整 PRD 状态）

        Returns:
            同步信息字符串
        """
        # 格式化已锁定共识
        locked_text = ""
        if self._debate_state.locked_consensus:
            locked_text = "### ✅ 已锁定共识（无需讨论，直接使用）\n"
            for p in self._debate_state.locked_consensus[-5:]:
                locked_text += f"- {p.content}\n"

        # 格式化待定共识
        pending_text = ""
        if self._debate_state.pending_consensus:
            pending_text = "### ◐ 待定共识（可完善细节）\n"
            for p in self._debate_state.pending_consensus[-3:]:
                pending_text += f"- {p.content}\n"

        # 格式化分歧点（重点）
        disagreements_text = self._format_disagreements()

        # 格式化 PRD 条目
        prd_items_text = ""
        if self._debate_state.prd_items:
            prd_items_text = "### 📝 已提取 PRD 条目\n"
            for item in self._debate_state.prd_items[-5:]:
                prd_items_text += f"- {item}\n"

        # 构建同步信息
        sync_info = f"""[中控同步 - 第 {self._debate_state.round_num} 轮]

## ⚠️ 议题提醒（必须遵守）
原始议题：{self._topic}
**禁止讨论与议题无关的内容。如有偏题，立即纠正。**

## 最新 PRD 状态

{locked_text}{pending_text}{prd_items_text}
### ❌ 当前分歧点（重点讨论）
{disagreements_text}

## 引导方向
请优先讨论分歧点，尝试提出折中方案。
- 如果分歧点已讨论充分，提出新的 PRD 条目
- 引用观点时从上方内容或对话历史中找依据，不要虚构

## 发言要求
[AGREE: xxx] - 你同意的观点（说明具体内容）
[PARTIAL_AGREE: xxx] - 部分同意（说明保留意见）
[DISAGREE: xxx] - 不同意（必须说明理由）
[PRD_ITEM] xxx - PRD 条目建议
"""
        return sync_info

    def _format_disagreements(self) -> str:
        """格式化分歧点（委托到 debate_points 模块）"""
        return format_disagreements(self._debate_state)

    def _quick_analyze_round(self, pm_content: str, dev_content: str) -> dict:
        """快速分析（委托到 debate_analysis 模块）"""
        return quick_analyze_round(pm_content, dev_content)

    async def _deep_analyze_rounds(self, recent_rounds: int = 2) -> dict:
        """深度分析 - LLM 语义理解（每 2-3 轮调用）

        Args:
            recent_rounds: 分析最近几轮

        Returns:
            分析结果字典
        """
        if not self._llm_client or not self._debate_state.debate_summary:
            return {}

        # 获取最近的辩论记录
        recent = self._debate_state.debate_summary[-recent_rounds:]
        if not recent:
            return {}

        pm_recent = "\n".join(r.get("pm_key_points", "") for r in recent)
        dev_recent = "\n".join(r.get("dev_key_points", "") for r in recent)

        # 使用 V2 Prompt（行业大牛视角）
        prd_draft_summary = (
            self._prd_draft.get_summary() if self._prd_draft else "暂无草稿"
        )

        prompt = MODERATOR_DEEP_ANALYSIS_PROMPT_V2.format(
            prd_draft_summary=prd_draft_summary,
            round_start=recent[0].get("round", 1),
            round_end=recent[-1].get("round", self._debate_state.round_num),
            pm_recent_content=pm_recent[:1000],
            dev_recent_content=dev_recent[:1000],
        )

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._llm_client.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            content = response.choices[0].message.content or ""
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                result = json.loads(json_match.group())
                self._apply_deep_analysis_result(result)
                return result
        except Exception as e:
            logger.error(f"深度分析失败 error={e}")

        return {}

    def _apply_deep_analysis_result(self, result: dict):
        """应用深度分析结果（委托到 debate_points 模块）"""
        apply_deep_analysis_result(
            self._debate_state, result, self._prd_draft, self._debate_state.round_num
        )

    def _process_new_markers(self, quick_result: dict) -> None:
        """处理新增标记 - 添加到 PRD 草稿

        Args:
            quick_result: _quick_analyze_round 返回的结果
        """
        if not self._prd_draft:
            return

        round_num = self._debate_state.round_num

        # 处理 [INFO] 标记 -> 待定议题（信息补充）
        for info in quick_result.get("new_info", []):
            self._prd_draft.add_item(
                section="待定议题",
                content=f"[信息] {info}",
                source="debater",
                round_num=round_num,
                confidence="medium",
            )

        # 处理 [CONSTRAINT] 标记 -> 技术约束
        # 技术约束来自开发者，通常有技术依据，置信度较高
        for constraint in quick_result.get("new_constraints", []):
            self._prd_draft.add_item(
                section="技术约束",
                content=constraint,
                source="debater",
                round_num=round_num,
                confidence="high",
            )

        # 处理 [RISK] 标记 -> 风险点
        for risk in quick_result.get("new_risks", []):
            self._prd_draft.add_item(
                section="风险点",
                content=risk,
                source="debater",
                round_num=round_num,
                confidence="medium",
            )

        # 处理 [SCENARIO] 标记 -> 目标用户（场景补充）
        for scenario in quick_result.get("new_scenarios", []):
            self._prd_draft.add_item(
                section="目标用户",
                content=f"[场景] {scenario}",
                source="debater",
                round_num=round_num,
                confidence="medium",
            )

        # 处理 [QUESTION] 标记 -> 待定议题
        for question in quick_result.get("new_questions", []):
            self._prd_draft.add_item(
                section="待定议题",
                content=f"[待回答] {question}",
                source="debater",
                round_num=round_num,
                confidence="low",
            )

    async def _generate_moderator_insight(
        self,
        topic: str,
        pm_position: str,
        dev_position: str,
        attempts: int,
    ) -> dict:
        """生成中控见解（行业大牛视角）

        Args:
            topic: 分歧议题
            pm_position: PM 立场
            dev_position: Dev 立场
            attempts: 讨论次数

        Returns:
            见解 JSON
        """
        if not self._llm_client:
            return {}

        insight = await self._moderator_tools.generate_insight(
            topic=topic,
            pm_position=pm_position[:200],
            dev_position=dev_position[:200],
            attempts=attempts,
            llm_client=self._llm_client,
        )

        return self._moderator_tools.get_insight_response() or {}

    def _format_insight(self, insight: dict) -> str:
        """格式化见解为可读文本

        Args:
            insight: 见解 JSON

        Returns:
            格式化后的文本
        """
        from .tools.moderator_tools import ModeratorInsight

        insight_obj = ModeratorInsight(
            topic=self._topic,
            industry_practice=insight.get("industry_practice", ""),
            pm_risks=insight.get("pm_risks", []),
            dev_risks=insight.get("dev_risks", []),
            compromise=insight.get("compromise", ""),
            recommendation=insight.get("recommendation", ""),
            reason=insight.get("reason", ""),
        )

        return self._moderator_tools.format_insight(insight_obj)

    async def run_full_debate_stream(self, topic: str):
        """完整流程流式输出

        Args:
            topic: 辩论议题

        Yields:
            事件流
        """
        self._topic = topic

        self._state = ModeratorState.CLARIFICATION

        self._clarification_moderator = ClarificationModerator(
            llm_client=self._llm_client,
            settings=self.settings,
        )

        async for event in self._clarification_moderator.start_clarification(topic):
            yield event
            if event.get("type") == "tool_call":
                # 遇到 tool_call，暂停，等待 CLI 处理后调用 resume_clarification()
                return
            if event.get("type") == "clarification_done":
                self._prd_base = event.get("prd_base", "")
                break

    async def resume_clarification(self):
        """继续澄清阶段（用户已提交回答后）

        Yields:
            事件流
        """
        async for event in self._clarification_moderator.continue_clarification():
            yield event
            if event.get("type") == "tool_call":
                return
            if event.get("type") == "clarification_done":
                self._prd_base = event.get("prd_base", "")
                # 澄清完成，开始辩论阶段
                async for debate_event in self._start_debate_phase():
                    yield debate_event
                return

    def submit_user_answer(self, answer: str):
        """提交用户回答（外部调用）

        Args:
            answer: 用户回答内容
        """
        if self._clarification_moderator:
            self._clarification_moderator.submit_user_answer(answer)

    async def _start_debate_phase(self):
        """开始辩论阶段"""
        from .debate_executor import DebateExecutor

        yield {"type": "phase_start", "phase": "debate"}
        self._state = ModeratorState.DEBATE

        self._prd_draft = PRDWorkingDraft(topic=self._topic)

        yield {
            "type": "moderator",
            "action": "debate_start",
            "content": f"辩论开始，请双方基于立场发表观点。\n\nPRD 基础版：\n{self._prd_base}",
        }

        executor = DebateExecutor(self)
        async for event in executor.run_free_debate(self._topic, self._prd_base):
            yield event

        yield {
            "type": "moderator",
            "action": "debate_end",
            "content": "辩论结束，开始综合双方观点生成 PRD。",
        }

        yield {"type": "phase_start", "phase": "synthesis"}
        self._state = ModeratorState.SYNTHESIS

        prd = self._generate_final_prd(self._topic)

        yield {
            "type": "debate_complete",
            "prd": prd,
            "rounds": self._debate_state.round_num,
            "reason": self._debate_state.termination_reason,
        }

        self._state = ModeratorState.COMPLETE
        logger.info(f"辩论阶段完成 rounds={self._debate_state.round_num}")

    async def _run_debate_autonomous_stream(self, topic: str, prd_base: str = ""):
        """自由辩论模式 - 通过 DebateExecutor 执行

        Args:
            topic: 辩论议题
            prd_base: PRD 基础版
        """
        from .debate_executor import DebateExecutor

        executor = DebateExecutor(self)
        async for event in executor.run_free_debate(topic, prd_base):
            yield event

    def submit_intervention(self, answer: str, category: str = None):
        """提交用户介入回答

        Args:
            answer: 用户回答
            category: 决策类别（可选）
        """
        self._pending_user_intervention = {
            "answer": answer,
            "category": category,
        }

    async def resume_debate(self):
        """恢复辩论（用户回答后）

        Yields:
            继续辩论的事件流
        """
        from .debate_executor import DebateExecutor

        executor = DebateExecutor(self)
        async for event in executor.continue_free_debate():
            yield event

    async def _continue_free_debate(self):
        """继续自由辩论（通过 DebateExecutor）"""
        from .debate_executor import DebateExecutor

        executor = DebateExecutor(self)
        async for event in executor.continue_free_debate():
            yield event

    def _generate_moderator_record(self, phase: str) -> dict:
        """生成 Moderator 记录事件"""
        agree_count = len(self._debate_state.agree_points)
        partial_count = len(self._debate_state.partial_agree_points)
        disagree_count = len(self._debate_state.disagreement_points)

        # 计算加权共识得分
        consensus_score = agree_count * 1.0 + partial_count * 0.5

        # 构建记录内容
        lines = [f"[{phase}] 共识进度"]

        if agree_count > 0:
            lines.append(f"  ✓ 完全共识({agree_count}):")
            for pt in self._debate_state.agree_points[-3:]:
                lines.append(f"    • {pt[:80]}")

        if partial_count > 0:
            lines.append(f"  ◐ 部分认同({partial_count}):")
            for pt in self._debate_state.partial_agree_points[-3:]:
                lines.append(f"    • {pt[:80]}")

        if disagree_count > 0:
            lines.append(f"  ✗ 待解决分歧({disagree_count}):")
            for pt in self._debate_state.disagreement_points[-3:]:
                lines.append(f"    • {pt[:80]}")

        lines.append(f"  📊 共识得分: {consensus_score:.1f}")

        return {
            "type": "moderator_record",
            "phase": phase,
            "content": "\n".join(lines),
            "agree_count": agree_count,
            "partial_count": partial_count,
            "disagree_count": disagree_count,
            "consensus_score": consensus_score,
        }

    def _generate_round_summary(self, analysis_result: dict = None) -> dict:
        """生成第一轮辩论总结事件

        Args:
            analysis_result: LLM 分析结果（可选）

        Returns:
            辩论总结事件字典
        """
        # 构建总结内容
        lines = ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
        lines.append("📊 第一轮辩论总结")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # 锁定共识
        locked = self._debate_state.locked_consensus
        if locked:
            lines.append("")
            lines.append("✅ 已达成共识（锁定）")
            for point in locked:
                lines.append(f"• {point.content}")

        # 待定共识
        pending = self._debate_state.pending_consensus
        if pending:
            lines.append("")
            lines.append("◐ 基本共识（可完善）")
            for point in pending:
                lines.append(f"• {point.content}")

        # 分歧点
        disagreements = self._debate_state.active_disagreements
        if disagreements:
            lines.append("")
            lines.append("❌ 当前分歧点")
            for d in disagreements:
                priority_mark = "[高优先]" if d.priority == "high" else ""
                lines.append(f"• {priority_mark} {d.topic}")
                if d.pm_position or d.dev_position:
                    lines.append(f"  PM: {d.pm_position[:50]}")
                    lines.append(f"  Dev: {d.dev_position[:50]}")

        # PRD 补充
        prd_updates = self._debate_state.prd_supplement
        if prd_updates:
            lines.append("")
            lines.append("📝 PRD 补充更新")
            for line in prd_updates.split("\n"):
                if line.strip():
                    lines.append(f"• {line.strip()}")

        # 引导方向
        if analysis_result and analysis_result.get("guidance"):
            lines.append("")
            lines.append(f"🎯 下轮引导：{analysis_result.get('guidance')}")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return {
            "type": "round_summary",
            "round": 1,
            "content": "\n".join(lines),
            "locked_count": len(locked),
            "pending_count": len(pending),
            "disagreement_count": len(disagreements),
            "guidance": analysis_result.get("guidance", "") if analysis_result else "",
        }

    def get_current_state(self) -> ModeratorState:
        """获取当前状态"""
        return self._state

    def get_pending_question(self) -> Optional[tuple[str, str]]:
        """获取当前待回答问题"""
        if self._state != ModeratorState.PRD_QUESTIONING:
            return None

        current_round = self._questioning_state.current_round
        if current_round >= len(self.DEFAULT_PRD_QUESTIONS):
            return None

        category, question = self.DEFAULT_PRD_QUESTIONS[current_round]
        return (category, question)

    def _get_next_speaker(self, current: DebaterAgent) -> DebaterAgent:
        """获取下一个发言者"""
        if current == self.debater1:
            return self.debater2
        else:
            return self.debater1

    def _check_termination(self) -> bool:
        """检查终止条件 - 核心议题共识覆盖判定"""
        MIN_ROUNDS_BEFORE_TERMINATION = 4

        if self._debate_state.round_num < MIN_ROUNDS_BEFORE_TERMINATION:
            return False

        # 轮数上限兜底
        if self._debate_state.round_num >= self.settings.max_rounds:
            self._debate_state.terminated = True
            self._debate_state.termination_reason = "达到轮数上限"
            return True

        # 基于结构化状态的判断
        locked_count = len(self._debate_state.locked_consensus)
        pending_count = len(self._debate_state.pending_consensus)
        active_disagreements = [
            d for d in self._debate_state.active_disagreements if not d.resolved
        ]
        high_priority_disagreements = [
            d for d in active_disagreements if d.priority == "high"
        ]

        # 条件1: 所有高优先分歧已解决
        if locked_count >= 3 and len(high_priority_disagreements) == 0:
            self._debate_state.terminated = True
            self._debate_state.termination_reason = "核心分歧已解决"
            return True

        # 条件2: 共识覆盖度高（锁定共识数 >= 分歧数 * 2）
        if locked_count >= len(active_disagreements) * 2 and locked_count >= 3:
            self._debate_state.terminated = True
            self._debate_state.termination_reason = "共识覆盖充分"
            return True

        # 兼容旧逻辑：基于 agree_points 计算
        agree_count = len(self._debate_state.agree_points)
        partial_count = len(self._debate_state.partial_agree_points)
        disagree_count = len(self._debate_state.disagreement_points)

        consensus_score = agree_count * 1.0 + partial_count * 0.5
        total_points = agree_count + partial_count + disagree_count

        if total_points == 0:
            return False

        coverage_ratio = consensus_score / (total_points + 0.1)

        # 条件3: 高共识覆盖 (>70%)
        if coverage_ratio >= 0.7 and consensus_score >= 3:
            self._debate_state.terminated = True
            self._debate_state.termination_reason = "核心议题共识覆盖"
            return True

        # 条件4: 充分辩论（轮数足够+观点充分）
        if self._debate_state.round_num >= 6 and total_points >= 5:
            self._debate_state.terminated = True
            if disagree_count > agree_count:
                self._debate_state.termination_reason = "分歧为主-充分辩论"
            else:
                self._debate_state.termination_reason = "共识为主-充分辩论"
            return True

        # 条件5: 僵局（连续N轮观点无实质推进）
        if self._debate_state.stalemate_count >= 2:
            # 不直接终止，返回 False 让深度分析处理
            return False

        return False

    def _quick_check_termination(self) -> dict:
        """快速终止检查 - 不调 LLM

        Returns:
            终止判断结果
        """
        result = {
            "should_terminate": False,
            "reason": "",
        }

        # 轮数上限
        if self._debate_state.round_num >= self.settings.max_rounds:
            result["should_terminate"] = True
            result["reason"] = "达到轮数上限"
            return result

        # 检查高优先分歧僵局
        active_disagreements = [
            d for d in self._debate_state.active_disagreements if not d.resolved
        ]
        high_priority_disagreements = [
            d for d in active_disagreements if d.priority == "high"
        ]

        if (
            all(d.attempts >= 3 for d in high_priority_disagreements)
            and high_priority_disagreements
        ):
            # 触发用户干预，不直接终止
            result["should_terminate"] = False
            result["need_intervention"] = True
            result["intervention_type"] = "stalemate"
            result["disagreement"] = high_priority_disagreements[0]
            return result

        return result

    def _generate_stalemate_intervention(self, disagreement: DisagreementPoint) -> dict:
        """生成僵局干预事件

        Args:
            disagreement: 僵局的分歧点

        Returns:
            干预事件字典
        """
        return {
            "type": "stalemate_intervention",
            "topic": disagreement.topic,
            "pm_position": disagreement.pm_position,
            "dev_position": disagreement.dev_position,
            "attempts": disagreement.attempts,
            "question": f"双方在 [{disagreement.topic}] 上僵持 {disagreement.attempts} 轮，请给出你的倾向或决策：",
            "options": [
                "支持 PM 立场",
                "支持 Dev 立场",
                "折中方案",
                "暂时搁置",
            ],
            "allow_skip": False,  # 僵局必须回答
        }

    def _generate_critical_decision_intervention(
        self, disagreement: DisagreementPoint
    ) -> dict:
        """生成关键决策干预事件

        Args:
            disagreement: 关键分歧点

        Returns:
            干预事件字典
        """
        CRITICAL_CATEGORIES = ["技术栈", "架构", "预算", "时间约束", "核心功能取舍"]

        if disagreement.category not in CRITICAL_CATEGORIES:
            return None

        return {
            "type": "critical_decision_intervention",
            "topic": disagreement.topic,
            "category": disagreement.category,
            "pm_position": disagreement.pm_position,
            "dev_position": disagreement.dev_position,
            "question": f"关于 [{disagreement.category}] 的关键决策：{disagreement.topic}",
            "options": self._get_decision_options(disagreement.category),
            "allow_skip": True,  # 可以跳过
        }

    def _get_decision_options(self, category: str) -> list[str]:
        """根据类别获取决策选项

        Args:
            category: 决策类别

        Returns:
            选项列表
        """
        options_map = {
            "技术栈": ["React", "Vue", "Angular", "原生开发", "其他方案"],
            "架构": ["微服务", "单体应用", "混合架构", "暂缓决策"],
            "预算": ["充足投入", "保守预算", "分期投入", "暂缓决策"],
            "时间约束": ["快速上线", "稳健推进", "分阶段交付", "暂缓决策"],
            "核心功能取舍": ["保留核心", "简化范围", "分阶段实现", "暂缓决策"],
        }
        return options_map.get(category, ["支持 PM", "支持 Dev", "折中", "跳过"])

    async def _inject_user_decision(self, decision: str, topic: str):
        """注入用户决策到辩论流程

        Args:
            decision: 用户决策内容
            topic: 分歧议题
        """
        # 1. 记录决策
        self._debate_state.user_decisions.append(
            {
                "topic": topic,
                "decision": decision,
                "round": self._debate_state.round_num,
            }
        )

        # 2. 发送给双方 Agent mailbox
        from .messaging.mailbox import send_to_agent

        injection_msg = f"""[Moderator 补充信息]

用户针对 [{topic}] 做出决策：
{decision}

请基于此约束继续讨论，无需再争论此议题。
"""
        await send_to_agent("moderator", "debater1", injection_msg)
        await send_to_agent("moderator", "debater2", injection_msg)

        # 3. 更新分歧状态
        disagreement = self._find_disagreement(topic)
        if disagreement:
            disagreement.resolved = True
            disagreement.resolution = f"用户决策：{decision}"

            # 4. 转为锁定共识
            self._debate_state.locked_consensus.append(
                ConsensusPoint(
                    content=f"{topic}：{decision}",
                    category=disagreement.category,
                    locked=True,
                    evidence=["用户决策"],
                    round_created=self._debate_state.round_num,
                )
            )

            # 兼容旧字段
            self._debate_state.agree_points.append(f"{topic}：{decision}")

    def _is_viewpoint_progressed(self, full_content: str) -> bool:
        """判断观点是否有实质性推进

        推进定义:
        - 提出新论据/数据
        - 改变立场或妥协
        - 提出具体解决方案
        """
        progress_indicators = [
            "因此",
            "所以",
            "建议",
            "方案",
            "妥协",
            "同意",
            "我们可以",
            "具体做法",
            "提出",
            "方案如下",
            "折中",
            "调整",
            "改进",
            "优化",
        ]

        has_progress = any(
            indicator in full_content for indicator in progress_indicators
        )
        has_new_prd = "[PRD_ITEM]" in full_content

        return has_progress or has_new_prd

    def _extract_points(self, content: str, topic: str = "") -> None:
        """从内容中提取共识点和分歧点（带去重，区分类型，验证相关性）

        Args:
            content: 发言内容
            topic: 辩论议题（用于验证相关性）
        """
        import re

        # 清理流式标记 [STREAM_END:xxx] 或 [STREAM_END]
        content = re.sub(r"\[STREAM_END:[^\]]*\]", "", content)
        content = re.sub(r"\[STREAM_END\]", "", content)

        # 提取议题关键词（用于相关性验证）
        topic_keywords = set(self._extract_keywords(topic)) if topic else set()

        def _is_relevant_to_topic(point: str) -> bool:
            """验证共识点是否与议题相关"""
            if not topic_keywords:
                return True  # 无议题时默认接受
            point_keywords = set(self._extract_keywords(point))
            overlap = len(point_keywords & topic_keywords)
            # 关键词重叠 >= 20% 视为相关
            return overlap >= len(topic_keywords) * 0.2 or len(point_keywords) == 0

        # 改进正则：匹配完整内容（支持嵌套 ]）
        # 格式1: [AGREE:content] - 有具体内容，使用改进正则支持嵌套括号
        # 格式2: [AGREE] - 仅标记（提取上下文句）
        agree_pattern_with_content = r"\[AGREE:([^\n\]]*(?:\][^\n\]]*)*)\]"
        agree_pattern_no_content = r"\[AGREE\](?!\s*:)"
        consensus_pattern_with_content = r"\[CONSENSUS:([^\n\]]*(?:\][^\n\]]*)*)\]"
        consensus_pattern_no_content = r"\[CONSENSUS\](?!\s*:)"
        partial_agree_pattern_with_content = (
            r"\[PARTIAL_AGREE:([^\n\]]*(?:\][^\n\]]*)*)\]"
        )
        partial_agree_pattern_no_content = r"\[PARTIAL_AGREE\](?!\s*:)"

        # AGREE - 完全共识（有内容）
        agree_matches = re.findall(agree_pattern_with_content, content, re.DOTALL)
        for match in agree_matches:
            point = match.strip()
            if point and point not in self._debate_state.agree_points:
                # 验证相关性：只添加与议题相关的共识
                if _is_relevant_to_topic(point):
                    self._debate_state.agree_points.append(point)
                    if point not in self._debate_state.consensus_points:
                        self._debate_state.consensus_points.append(point)

        # AGREE - 完全共识（无内容时提取前后文）
        agree_no_content_matches = re.findall(agree_pattern_no_content, content)
        for _ in agree_no_content_matches:
            context_match = re.search(r"([^\n]{0,50})\[AGREE\]", content)
            if context_match:
                point = context_match.group(1).strip() or "同意"
                if point not in self._debate_state.agree_points:
                    # 验证相关性
                    if _is_relevant_to_topic(point):
                        self._debate_state.agree_points.append(point)
                        if point not in self._debate_state.consensus_points:
                            self._debate_state.consensus_points.append(point)

        # CONSENSUS - 完全共识（同AGREE处理）
        consensus_matches = re.findall(
            consensus_pattern_with_content, content, re.DOTALL
        )
        for match in consensus_matches:
            point = match.strip()
            if point and point not in self._debate_state.agree_points:
                # 验证相关性
                if _is_relevant_to_topic(point):
                    self._debate_state.agree_points.append(point)
                    if point not in self._debate_state.consensus_points:
                        self._debate_state.consensus_points.append(point)

        consensus_no_content_matches = re.findall(consensus_pattern_no_content, content)
        for _ in consensus_no_content_matches:
            context_match = re.search(r"([^\n]{0,50})\[CONSENSUS\]", content)
            if context_match:
                point = context_match.group(1).strip() or "共识"
                if point not in self._debate_state.agree_points:
                    # 验证相关性
                    if _is_relevant_to_topic(point):
                        self._debate_state.agree_points.append(point)
                        if point not in self._debate_state.consensus_points:
                            self._debate_state.consensus_points.append(point)

        # PARTIAL_AGREE - 部分共识（有内容）
        partial_matches = re.findall(
            partial_agree_pattern_with_content, content, re.DOTALL
        )
        for match in partial_matches:
            point = match.strip()
            if point and point not in self._debate_state.partial_agree_points:
                # 验证相关性
                if _is_relevant_to_topic(point):
                    self._debate_state.partial_agree_points.append(point)
                    if point not in self._debate_state.consensus_points:
                        self._debate_state.consensus_points.append(point)

        # PARTIAL_AGREE - 部分共识（无内容时提取前后文）
        partial_no_content_matches = re.findall(
            partial_agree_pattern_no_content, content
        )
        for _ in partial_no_content_matches:
            context_match = re.search(r"([^\n]{0,50})\[PARTIAL_AGREE\]", content)
            if context_match:
                point = context_match.group(1).strip() or "部分认同"
                if point not in self._debate_state.partial_agree_points:
                    # 验证相关性
                    if _is_relevant_to_topic(point):
                        self._debate_state.partial_agree_points.append(point)
                        if point not in self._debate_state.consensus_points:
                            self._debate_state.consensus_points.append(point)

        # 提取分歧点（DISAGREE）- 支持两种格式，改进正则支持嵌套括号
        disagree_pattern_with_content = r"\[DISAGREE:([^\n\]]*(?:\][^\n\]]*)*)\]"
        disagree_pattern_no_content = r"\[DISAGREE\](?!\s*:)"

        disagree_matches = re.findall(disagree_pattern_with_content, content, re.DOTALL)
        for match in disagree_matches:
            point = match.strip()
            if point and point not in self._debate_state.disagreement_points:
                self._debate_state.disagreement_points.append(point)

        disagree_no_content_matches = re.findall(disagree_pattern_no_content, content)
        for _ in disagree_no_content_matches:
            context_match = re.search(r"([^\n]{0,50})\[DISAGREE\]", content)
            if context_match:
                point = context_match.group(1).strip() or "分歧"
                if point not in self._debate_state.disagreement_points:
                    self._debate_state.disagreement_points.append(point)

        # Fallback：检查是否有任何匹配
        has_any_match = (
            agree_matches
            or agree_no_content_matches
            or consensus_matches
            or consensus_no_content_matches
            or partial_matches
            or partial_no_content_matches
            or disagree_matches
            or disagree_no_content_matches
        )

        if not has_any_match:
            problem_pattern = r"###?\s*(问题\d|反驳点|挑战)[：:\s]*([^\n]+)"
            problem_matches = re.findall(problem_pattern, content)

            if problem_matches:
                for match in problem_matches:
                    point = f"{match[0]}: {match[1][:100]}"
                    if point not in self._debate_state.disagreement_points:
                        self._debate_state.disagreement_points.append(point)
            else:
                first_para = content.split("\n\n")[0] if "\n\n" in content else content
                stance = first_para.strip()[:80]
                if stance and stance not in self._debate_state.disagreement_points:
                    self._debate_state.disagreement_points.append(stance)

    def _extract_prd_items(self, content: str) -> list[str]:
        """从内容中提取PRD条目（显式标记 + 智能提炼）

        Args:
            content: 发言内容

        Returns:
            提取的新PRD条目列表（去重后）
        """
        import re

        # 清理流式标记
        content = re.sub(r"\[STREAM_END:[^\]]*\]", "", content)
        content = re.sub(r"\[STREAM_END\]", "", content)

        # 1. 显式标记 [PRD_ITEM]
        explicit_pattern = r"\[PRD_ITEM\]\s*([^\n]+)"
        explicit_items = re.findall(explicit_pattern, content)

        # 2. 智能提炼：从关键词提取
        implicit_patterns = [
            r"建议[:：]\s*([^\n。]{10,50})",
            r"应该[:：]\s*([^\n。]{10,50})",
            r"需要[:：]\s*([^\n。]{10,50})",
            r"功能[:：]\s*([^\n。]{10,50})",
            r"实现[:：]\s*([^\n。]{10,50})",
            r"目标[:：]\s*([^\n。]{10,50})",
        ]

        implicit_items = []
        for pattern in implicit_patterns:
            matches = re.findall(pattern, content)
            implicit_items.extend(matches)

        # 合并去重
        all_items = explicit_items + implicit_items
        new_items = []
        for item in all_items:
            item_clean = item.strip()
            if item_clean and len(item_clean) >= 10:
                if item_clean not in self._debate_state.prd_items:
                    self._debate_state.prd_items.append(item_clean)
                    new_items.append(item_clean)

        return new_items

    def _detect_off_topic(self, recent_msgs: list[str], topic: str) -> dict:
        """偏题检测（委托到 debate_analysis 模块）"""
        result = detect_off_topic(recent_msgs, topic, self._extract_keywords)
        if result["is_off_topic"] and result.get("msg"):
            result["guidance"] = self._generate_guidance(topic, result.get("msg", ""))
        return result

    def _detect_hallucinated_reference(self, msg: str, topic: str) -> str | None:
        """幻觉检测（委托到 debate_analysis 模块）"""
        return detect_hallucinated_reference(msg, topic, self._extract_keywords)

    def _extract_keywords(self, text: str) -> list[str]:
        """提取关键词（委托到 debate_analysis 模块）"""
        return extract_keywords(text)

    def _detect_critical_decision(self, recent_messages: list[str]) -> Optional[dict]:
        """检测关键决策点（委托到 debate_analysis 模块）"""
        result = detect_critical_decision(recent_messages, self._asked_decisions)
        if result and self._debate_state.disagreement_points:
            result["options"] = self._get_decision_options(result["category"])
        return result

    def _get_decision_options(self, category: str) -> list[str]:
        """获取决策选项（委托到 debate_analysis 模块）"""
        return get_decision_options(category)

    def _generate_stalemate_question(self) -> dict:
        """生成僵局询问

        Returns:
            僵局询问事件数据
        """
        # 获取最近分歧点
        disagreements = self._debate_state.disagreement_points[-3:]
        disagreement_summary = (
            "\n".join(f"• {d[:100]}" for d in disagreements)
            if disagreements
            else "双方观点差异"
        )

        return {
            "type": "stalemate_question",
            "topic": self._topic,
            "disagreements": disagreement_summary,
            "rounds": self._debate_state.round_num,
            "question": f"辩论已进行 {self._debate_state.round_num} 轮，双方僵持不下。\n请您给出看法或倾向，帮助打破僵局：",
        }

    def _generate_guidance(self, topic: str, off_topic_content: str) -> str:
        """生成引导消息"""
        core_features = self._questioning_state.answers.get("核心功能", "核心议题")

        return f"""[Moderator引导] 辩论似乎偏离了议题。

当前议题: {topic}
偏题内容摘要: {off_topic_content[:100]}...

建议回归以下核心讨论点:
{core_features}

请双方围绕议题继续讨论。
"""

    def _generate_prd_base(self) -> str:
        """从问答生成PRD基础版"""
        answers = self._questioning_state.answers

        return f"""# PRD基础版

## 目标用户
{answers.get("目标用户", "待补充")}

## 核心功能
{answers.get("核心功能", "待补充")}

## 解决的问题
{answers.get("解决问题", "待补充")}

## 成功指标
{answers.get("成功指标", "待补充")}

## 约束条件
{answers.get("约束条件", "无")}

---
*通过问答对话生成，将在辩论中完善*
"""

    def _generate_final_prd(self, topic: str) -> str:
        """生成最终PRD（优化格式）

        包含：精简概述 + 分类PRD条目 + 共识/分歧分析
        """
        # 去重后的共识和分歧
        unique_consensus = list(dict.fromkeys(self._debate_state.consensus_points))
        unique_disagreement = list(
            dict.fromkeys(self._debate_state.disagreement_points[-10:])
        )

        # PRD条目分类
        prd_items = getattr(self._debate_state, "prd_items", [])
        categorized_items = self._categorize_prd_items(prd_items)

        # 精简概述（只取PRD基础版的前300字）
        overview = self._prd_base if self._prd_base else "待完善"

        return f"""# PRD: {topic}

## 概述
{overview}

## PRD 条目（辩论提取）

{categorized_items}

## 达成的共识

{self._format_consensus(unique_consensus)}

## 待解决的分歧

{self._format_disagreement(unique_disagreement)}

## 实现建议

1. **平衡双方观点** - 在产品价值和技术可行性之间寻找平衡点
2. **分阶段实现** - MVP优先验证核心功能，后续迭代完善
3. **明确边界** - 确定功能边界，避免过度开发

---

*辩论轮数: {self._debate_state.round_num}* | *结束原因: {self._debate_state.termination_reason}* | *PRD条目数: {len(prd_items)}*
"""

    def _categorize_prd_items(self, items: list[str]) -> str:
        """分类PRD条目（委托到 debate_points 模块）"""
        return categorize_prd_items(items)

    def _format_consensus(self, points: list[str]) -> str:
        """格式化共识点（委托到 debate_points 模块）"""
        return format_consensus(points)

    def _format_disagreement(self, points: list[str]) -> str:
        """格式化分歧点（委托到 debate_points 模块）"""
        return format_disagreement(points)


async def run_debate(
    topic: str,
    llm_client,
    preset: str = "pm_vs_dev",
    settings: Settings = None,
) -> str:
    """运行辩论的便捷函数"""
    reset_message_router()

    debater1, debater2 = create_debater_pair(
        llm_client=llm_client,
        preset_name=preset,
        memory_scope="project",
    )

    moderator = DebateModerator(
        debater1=debater1,
        debater2=debater2,
        settings=settings,
    )

    # 运行完整流程
    prd = await moderator.run_debate(topic)
    return prd


# ========== 流式输出支持 ==========


async def run_debate_stream(
    topic: str,
    llm_client,
    preset: str = "pm_vs_dev",
    settings: Settings = None,
    ask_user_tool=None,
):
    """流式运行完整辩论流程

    Yields:
        辩论消息事件
    """
    reset_message_router()

    debater1, debater2 = create_debater_pair(
        llm_client=llm_client,
        preset_name=preset,
        memory_scope="project",
    )

    moderator = DebateModerator(
        debater1=debater1,
        debater2=debater2,
        llm_client=llm_client,
        settings=settings,
        ask_user_tool=ask_user_tool,
    )

    # 运行完整流程
    async for event in moderator.run_full_debate_stream(topic):
        yield event
