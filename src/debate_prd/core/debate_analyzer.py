"""辩论分析器 - LLM 语义分析逻辑

从 debate_loop.py 拆分，负责：
- 第一轮分析（_analyze_first_round）
- 深度分析（_deep_analyze_rounds）
- 快速分析（_quick_analyze_round）
- 分析结果应用

关键改进：
- 函数长度不超过 50 行
- 统一使用 logging 替代 print
"""

import json
import re
from typing import TYPE_CHECKING

from .logger import get_logger

if TYPE_CHECKING:
    from .debate_loop import DebateModerator

logger = get_logger("analyzer")


class DebateAnalyzer:
    """辩论分析器 - LLM 语义理解"""

    def __init__(self, moderator: "DebateModerator"):
        self._moderator = moderator
        self._state = moderator._debate_state

    async def analyze_first_round(self, pm_content: str, dev_content: str) -> dict:
        """第一轮中控 LLM 分析

        Args:
            pm_content: PM 第一轮发言
            dev_content: Dev 第一轮发言

        Returns:
            分析结果字典
        """
        if not self._moderator._llm_client:
            return {}

        prompt = self._build_first_round_prompt(pm_content, dev_content)

        try:
            response = await self._moderator._llm_client.chat.completions.create(
                model=self._moderator._llm_client.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            content = response.choices[0].message.content or ""
            result = self._extract_json_from_response(content)

            self._apply_first_round_result(result)
            logger.info(
                f"第一轮分析完成 locked={len(self._state.locked_consensus)} pending={len(self._state.pending_consensus)}"
            )
            return result

        except Exception as e:
            logger.error(f"第一轮分析失败 error={e}")
            return {}

    def _build_first_round_prompt(self, pm_content: str, dev_content: str) -> str:
        """构建第一轮分析 prompt"""
        from ..config.prompts import MODERATOR_ANALYSIS_PROMPT

        return MODERATOR_ANALYSIS_PROMPT.format(
            prd_base=self._moderator._prd_base,
            pm_content=pm_content,
            dev_content=dev_content,
        )

    def _extract_json_from_response(self, content: str) -> dict:
        """从响应中提取 JSON"""
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            return json.loads(json_match.group())
        return json.loads(content)

    def _apply_first_round_result(self, analysis: dict):
        """应用第一轮分析结果"""
        self._update_locked_consensus(analysis.get("locked_consensus", []))
        self._update_pending_consensus(analysis.get("pending_consensus", []))
        self._update_disagreements(analysis.get("active_disagreements", []))
        self._update_prd_supplement(analysis.get("prd_supplement_updates", []))
        self._sync_legacy_fields()

    def _update_locked_consensus(self, items: list):
        """更新锁定共识"""
        for item in items:
            point = self._create_consensus_point(item, locked=True)
            if point.content and point not in self._state.locked_consensus:
                self._state.locked_consensus.append(point)

    def _update_pending_consensus(self, items: list):
        """更新待定共识"""
        for item in items:
            point = self._create_consensus_point(item, locked=False)
            if point.content and point not in self._state.pending_consensus:
                self._state.pending_consensus.append(point)

    def _create_consensus_point(self, item: dict, locked: bool):
        """创建共识点"""
        from .debate_loop import ConsensusPoint

        return ConsensusPoint(
            content=item.get("content", ""),
            category=item.get("category", ""),
            locked=locked,
            evidence=item.get("evidence", []),
            round_created=self._state.round_num,
        )

    def _update_disagreements(self, items: list):
        """更新分歧点"""
        for item in items:
            from .debate_loop import DisagreementPoint

            disagreement = DisagreementPoint(
                topic=item.get("topic", ""),
                pm_position=item.get("pm_position", ""),
                dev_position=item.get("dev_position", ""),
                priority=item.get("priority", "normal"),
                category=item.get("category", ""),
                round_created=self._state.round_num,
                attempts=0,
            )
            if disagreement.topic:
                existing = self._find_disagreement(disagreement.topic)
                if existing:
                    existing.pm_position = disagreement.pm_position
                    existing.dev_position = disagreement.dev_position
                else:
                    self._state.active_disagreements.append(disagreement)

    def _find_disagreement(self, topic: str):
        """查找已存在的分歧点"""
        for d in self._state.active_disagreements:
            if d.topic == topic or topic in d.topic or d.topic in topic:
                return d
        return None

    def _update_prd_supplement(self, updates: list):
        """更新 PRD 补充版"""
        if updates:
            self._state.prd_supplement = "\n".join(updates)

    def _sync_legacy_fields(self):
        """同步旧字段（兼容）"""
        for point in self._state.locked_consensus:
            if point.content not in self._state.agree_points:
                self._state.agree_points.append(point.content)
        for point in self._state.pending_consensus:
            if point.content not in self._state.partial_agree_points:
                self._state.partial_agree_points.append(point.content)

    async def deep_analyze_rounds(self, recent_rounds: int = 2) -> dict:
        """深度分析 - LLM 语义理解

        Args:
            recent_rounds: 分析最近几轮

        Returns:
            分析结果字典
        """
        if not self._moderator._llm_client or not self._state.debate_summary:
            return {}

        recent = self._state.debate_summary[-recent_rounds:]
        if not recent:
            return {}

        prompt = self._build_deep_analysis_prompt(recent, recent_rounds)

        try:
            response = await self._moderator._llm_client.chat.completions.create(
                model=self._moderator._llm_client.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            content = response.choices[0].message.content or ""
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                result = json.loads(json_match.group())
                self._apply_deep_analysis_result(result)
                logger.info(f"深度分析完成 rounds={recent_rounds}")
                return result
        except Exception as e:
            logger.error(f"深度分析失败 error={e}")

        return {}

    def _build_deep_analysis_prompt(self, recent: list, recent_rounds: int) -> str:
        """构建深度分析 prompt"""
        from ..config.prompts import MODERATOR_DEEP_ANALYSIS_PROMPT_V2

        pm_recent = "\n".join(r.get("pm_key_points", "") for r in recent)
        dev_recent = "\n".join(r.get("dev_key_points", "") for r in recent)

        prd_draft_summary = (
            self._moderator._prd_draft.get_summary()
            if self._moderator._prd_draft
            else "暂无草稿"
        )

        return MODERATOR_DEEP_ANALYSIS_PROMPT_V2.format(
            prd_draft_summary=prd_draft_summary,
            round_start=recent[0].get("round", 1),
            round_end=recent[-1].get("round", self._state.round_num),
            pm_recent_content=pm_recent[:1000],
            dev_recent_content=dev_recent[:1000],
        )

    def _apply_deep_analysis_result(self, result: dict):
        """应用深度分析结果"""
        self._resolve_disagreements(result.get("resolved_disagreements", []))
        self._update_disagreement_status(result.get("updated_disagreements", []))
        self._add_new_locked_consensus(result.get("new_locked_consensus", []))
        self._apply_prd_updates(result.get("prd_updates", []))

    def _resolve_disagreements(self, items: list):
        """处理已解决的分歧"""
        for item in items:
            topic = item.get("topic", "")
            disagreement = self._find_disagreement(topic)
            if disagreement:
                disagreement.resolved = True
                disagreement.resolution = item.get("resolution", "")
                if item.get("becomes_consensus"):
                    self._add_resolution_as_consensus(disagreement)

    def _add_resolution_as_consensus(self, disagreement):
        """将解决结果转为共识"""
        from .debate_loop import ConsensusPoint

        self._state.locked_consensus.append(
            ConsensusPoint(
                content=disagreement.resolution,
                category=disagreement.category,
                locked=True,
                round_created=self._state.round_num,
            )
        )

    def _update_disagreement_status(self, items: list):
        """更新分歧状态"""
        for item in items:
            topic = item.get("topic", "")
            disagreement = self._find_disagreement(topic)
            if disagreement:
                if item.get("pm_position"):
                    disagreement.pm_position = item.get("pm_position")
                if item.get("dev_position"):
                    disagreement.dev_position = item.get("dev_position")
                disagreement.attempts = item.get("attempts", disagreement.attempts)

    def _add_new_locked_consensus(self, contents: list):
        """添加新的锁定共识"""
        from .debate_loop import ConsensusPoint

        for content in contents:
            if content:
                point = ConsensusPoint(
                    content=content,
                    locked=True,
                    round_created=self._state.round_num,
                )
                if point not in self._state.locked_consensus:
                    self._state.locked_consensus.append(point)

    def _apply_prd_updates(self, updates: list):
        """应用 PRD 更新"""
        for update in updates:
            if not update:
                continue

            if isinstance(update, dict):
                self._apply_structured_prd_update(update)
            else:
                self._apply_simple_prd_update(str(update))

    def _apply_structured_prd_update(self, update: dict):
        """应用结构化 PRD 更新"""
        section = update.get("section", "核心功能")
        content = update.get("content", "")
        source = update.get("source", "moderator")
        confidence = update.get("confidence", "medium")

        if content and self._moderator._prd_draft:
            self._moderator._prd_draft.add_item(
                section=section,
                content=content,
                source=source,
                round_num=self._state.round_num,
                confidence=confidence,
            )

        if self._state.prd_supplement:
            self._state.prd_supplement += f"\n{content}"
        else:
            self._state.prd_supplement = content

    def _apply_simple_prd_update(self, update: str):
        """应用简单 PRD 更新"""
        if self._state.prd_supplement:
            self._state.prd_supplement += f"\n{update}"
        else:
            self._state.prd_supplement = update

    def quick_analyze_round(self, pm_content: str, dev_content: str) -> dict:
        """快速分析 - 正则提取标记

        Args:
            pm_content: PM 本轮发言
            dev_content: Dev 本轮发言

        Returns:
            分析结果字典
        """
        result = {
            "new_agrees": [],
            "new_disagrees": [],
            "new_prd_items": [],
            "new_info": [],
            "new_constraints": [],
            "new_risks": [],
            "new_scenarios": [],
            "new_questions": [],
            "progress_detected": False,
        }

        patterns = self._get_extraction_patterns()

        for content in [pm_content, dev_content]:
            self._extract_markers(content, patterns, result)

        self._detect_progress(pm_content, dev_content, result)

        return result

    def _get_extraction_patterns(self) -> dict:
        """获取提取正则"""
        return {
            "agree": r"\[AGREE:([^\n\]]*(?:\][^\n\]]*)*)\]",
            "disagree": r"\[DISAGREE:([^\n\]]*(?:\][^\n\]]*)*)\]",
            "prd": r"\[PRD_ITEM\] ([^\n]+)",
            "info": r"\[INFO\] ([^\n]+)",
            "constraint": r"\[CONSTRAINT\] ([^\n]+)",
            "risk": r"\[RISK\] ([^\n]+)",
            "scenario": r"\[SCENARIO\] ([^\n]+)",
            "question": r"\[QUESTION\] ([^\n]+)",
        }

    def _extract_markers(self, content: str, patterns: dict, result: dict):
        """提取标记"""
        for key, pattern in patterns.items():
            matches = re.findall(pattern, content, re.DOTALL)
            target_key = f"new_{key}s" if key in ["agree", "disagree"] else f"new_{key}"
            for match in matches:
                item = match.strip() if isinstance(match, str) else match[0].strip()
                if item and item not in result[target_key]:
                    result[target_key].append(item)

    def _detect_progress(self, pm_content: str, dev_content: str, result: dict):
        """检测进展"""
        indicators = ["折中", "方案", "建议", "同意", "调整", "优化", "妥协"]
        for content in [pm_content, dev_content]:
            if any(indicator in content for indicator in indicators):
                result["progress_detected"] = True
                break
