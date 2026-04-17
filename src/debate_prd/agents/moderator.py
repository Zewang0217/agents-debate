"""中控 Agent：引导、协调、记录、生成 PRD"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Sequence

from autogen_agentchat.agents import BaseChatAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import TextMessage, BaseChatMessage
from autogen_core import CancellationToken
from autogen_core.models import ChatCompletionClient

from ..config.settings import Settings
from ..config.prompts import (
    build_moderator_system_message,
    build_clarification_prompt,
    build_intervention_prompt,
)


class ModeratorState(Enum):
    """中控 Agent 状态"""
    CLARIFICATION = "clarification"    # 澄清需求阶段
    DEBATE = "debate"                  # 辩论阶段
    INTERVENTION = "intervention"      # 用户介入阶段
    SYNTHESIS = "synthesis"            # 综合 PRD 阶段
    COMPLETE = "complete"              # 完成


@dataclass
class DebateRecord:
    """辩论记录"""
    round_num: int
    debater1_view: str
    debater2_view: str
    consensus_points: list[str] = field(default_factory=list)
    disagreement_points: list[str] = field(default_factory=list)


class ModeratorAgent(BaseChatAgent):
    """中控 Agent

    负责引导用户澄清需求、协调辩论流程、记录观点、
    判断用户介入时机、生成最终 PRD。

    状态机:
    CLARIFICATION → DEBATE → (INTERVENTION) → SYNTHESIS → COMPLETE

    特殊标记:
    - `[CLARIFICATION_DONE]` - 澄清完成
    - `[REQUEST_USER]` - 请求用户介入
    - `[PRD_COMPLETE]` - PRD 完成
    """

    def __init__(
        self,
        name: str,
        model_client: ChatCompletionClient,
        settings: Settings = None,
    ):
        """初始化中控 Agent

        Args:
            name: Agent 名称
            model_client: LLM 客户端
            settings: 配置参数
        """
        super().__init__(
            name=name,
            description="中控 Agent：协调辩论、记录观点、生成 PRD",
        )
        self._model_client = model_client
        self._settings = settings or Settings()
        self._state = ModeratorState.CLARIFICATION

        # 辩论记录
        self._debate_records: list[DebateRecord] = []
        self._all_consensus: list[str] = []
        self._all_disagreements: list[str] = []
        self._clarified_requirements: str = ""
        self._round_count: int = 0
        self._stalemate_count: int = 0  # 僵局计数

        # 收集的需求信息
        self._topic: str = ""
        self._target_users: str = ""
        self._core_features: str = ""
        self._constraints: str = ""

    @property
    def produced_message_types(self) -> Sequence[type[BaseChatMessage]]:
        return (TextMessage,)

    async def on_messages(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: CancellationToken,
    ) -> Response:
        """处理消息，基于状态机逻辑"""
        last_message = messages[-1] if messages else None
        content = last_message.content if last_message else ""

        if self._state == ModeratorState.CLARIFICATION:
            return await self._handle_clarification(messages, cancellation_token)

        elif self._state == ModeratorState.DEBATE:
            return await self._handle_debate(messages, cancellation_token)

        elif self._state == ModeratorState.INTERVENTION:
            return await self._handle_intervention(messages, cancellation_token)

        elif self._state == ModeratorState.SYNTHESIS:
            return await self._handle_synthesis(messages, cancellation_token)

        elif self._state == ModeratorState.COMPLETE:
            return Response(
                chat_message=TextMessage(
                    content="辩论已完成，PRD 已生成。",
                    source=self.name,
                )
            )

        # 默认：推进辩论
        return Response(
            chat_message=TextMessage(
                content="请继续辩论。",
                source=self.name,
            )
        )

    async def on_reset(self, cancellation_token: CancellationToken) -> None:
        """重置状态"""
        self._state = ModeratorState.CLARIFICATION
        self._debate_records.clear()
        self._all_consensus.clear()
        self._all_disagreements.clear()
        self._round_count = 0
        self._stalemate_count = 0

    # ========== 状态处理方法 ==========

    async def _handle_clarification(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: CancellationToken,
    ) -> Response:
        """处理澄清阶段"""
        last_msg = messages[-1] if messages else None
        content = last_msg.content if last_msg else ""

        # 检查是否完成澄清
        if "[CLARIFICATION_DONE]" in str(content):
            self._state = ModeratorState.DEBATE
            self._clarified_requirements = self._extract_requirements(messages)
            return Response(
                chat_message=TextMessage(
                    content=f"需求已澄清，开始辩论。\n\n需求摘要：\n{self._clarified_requirements}\n\n请双方开始辩论。",
                    source=self.name,
                )
            )

        # 收集需求信息
        if "目标用户" in str(content) or "target user" in str(content).lower():
            self._target_users = str(content)
        elif "核心功能" in str(content) or "core feature" in str(content).lower():
            self._core_features = str(content)
        elif "约束" in str(content) or "constraint" in str(content).lower():
            self._constraints = str(content)

        # 继续引导澄清
        return Response(
            chat_message=TextMessage(
                content=self._generate_clarification_response(messages),
                source=self.name,
            )
        )

    async def _handle_debate(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: CancellationToken,
    ) -> Response:
        """处理辩论阶段"""
        self._round_count += 1

        # 记录本轮辩论
        record = self._extract_debate_record(messages)
        self._debate_records.append(record)

        # 更新共识和分歧
        self._all_consensus.extend(record.consensus_points)
        self._all_disagreements.extend(record.disagreement_points)

        # 检查是否需要用户介入
        if self._check_intervention_needed(messages):
            self._state = ModeratorState.INTERVENTION
            return Response(
                chat_message=TextMessage(
                    content=self._build_intervention_request(),
                    source=self.name,
                )
            )

        # 检查是否达成共识
        if self._check_consensus_reached():
            self._state = ModeratorState.SYNTHESIS
            return Response(
                chat_message=TextMessage(
                    content="双方已达成主要共识，开始生成 PRD。",
                    source=self.name,
                )
            )

        # 继续辩论
        return Response(
            chat_message=TextMessage(
                content=self._generate_debate_coordination(messages),
                source=self.name,
            )
        )

    async def _handle_intervention(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: CancellationToken,
    ) -> Response:
        """处理用户介入阶段"""
        # 检查用户回复
        for msg in messages:
            if "user" in msg.source.lower() or "仲裁" in str(msg.content):
                # 记录用户决策
                decision = str(msg.content)
                self._all_consensus.append(f"用户决策: {decision}")
                self._state = ModeratorState.DEBATE
                return Response(
                    chat_message=TextMessage(
                        content=f"用户决策已记录：{decision}\n请继续辩论。",
                        source=self.name,
                    )
                )

        # 继续等待用户回复
        return Response(
            chat_message=TextMessage(
                content="[REQUEST_USER] 请用户做出决策。",
                source=self.name,
            )
        )

    async def _handle_synthesis(
        self,
        messages: Sequence[BaseChatMessage],
        cancellation_token: CancellationToken,
    ) -> Response:
        """处理综合阶段 - 生成 PRD"""
        prd_content = self._generate_prd()

        self._state = ModeratorState.COMPLETE

        return Response(
            chat_message=TextMessage(
                content=f"[PRD_COMPLETE]\n\n{prd_content}",
                source=self.name,
            )
        )

    # ========== 检查方法 ==========

    def _check_intervention_needed(self, messages: Sequence[BaseChatMessage]) -> bool:
        """检查是否需要用户介入"""
        # 1. 轮数上限
        if self._round_count >= self._settings.max_rounds:
            return True

        # 2. Agent 主动请求
        for msg in messages:
            if "[REQUEST_ARBITRATION]" in str(msg.content):
                return True

        # 3. 僵局检测（连续多轮无新观点）
        if self._detect_stalemate(messages):
            self._stalemate_count += 1
            if self._stalemate_count >= self._settings.stalemate_rounds:
                return True
        else:
            self._stalemate_count = 0

        # 4. 业务决策需要（检测关键词）
        for msg in messages:
            content = str(msg.content)
            if any(kw in content for kw in ["优先级", "取舍", "选择", "决定"]):
                if "无法" in content or "分歧" in content:
                    return True

        return False

    def _detect_stalemate(self, messages: Sequence[BaseChatMessage]) -> bool:
        """检测辩论僵局"""
        if len(self._debate_records) < 2:
            return False

        # 简化检测：检查最近两轮是否有实质进展
        last_record = self._debate_records[-1]
        if not last_record.consensus_points and not last_record.disagreement_points:
            return True

        return False

    def _check_consensus_reached(self) -> bool:
        """检查是否达成共识"""
        # 计算共识比例
        total_issues = len(self._all_consensus) + len(self._all_disagreements)
        if total_issues == 0:
            return False

        consensus_ratio = len(self._all_consensus) / total_issues
        return consensus_ratio >= self._settings.consensus_threshold

    # ========== 辅助方法 ==========

    def _extract_requirements(self, messages: Sequence[BaseChatMessage]) -> str:
        """从消息中提取需求摘要"""
        # 简化：收集非 Agent 消息作为需求描述
        user_messages = [
            str(msg.content)
            for msg in messages
            if "debater" not in msg.source.lower() and "moderator" not in msg.source.lower()
        ]
        return "\n".join(user_messages[-5:])  # 最近 5 条用户消息

    def _extract_debate_record(self, messages: Sequence[BaseChatMessage]) -> DebateRecord:
        """从消息中提取辩论记录"""
        debater1_views = []
        debater2_views = []
        consensus = []
        disagreements = []

        for msg in messages[-4:]:  # 最近 4 条消息（两轮辩论）
            content = str(msg.content)
            if "debater1" in msg.source.lower():
                debater1_views.append(content)
                if "[AGREE]" in content:
                    consensus.append(content.replace("[AGREE]", "").strip())
            elif "debater2" in msg.source.lower():
                debater2_views.append(content)
                if "[AGREE]" in content:
                    consensus.append(content.replace("[AGREE]", "").strip())

        # 简化：检测分歧关键词
        all_content = " ".join(debater1_views + debater2_views)
        if "不同意" in all_content or "反对" in all_content:
            disagreements.append("双方存在分歧")

        return DebateRecord(
            round_num=self._round_count,
            debater1_view="\n".join(debater1_views),
            debater2_view="\n".join(debater2_views),
            consensus_points=consensus,
            disagreement_points=disagreements,
        )

    def _generate_clarification_response(self, messages: Sequence[BaseChatMessage]) -> str:
        """生成澄清引导响应"""
        if not self._target_users:
            return "这个产品/功能的目标用户是谁？请描述用户画像。"
        elif not self._core_features:
            return "核心功能是什么？请列出主要功能点。"
        elif not self._constraints:
            return "有什么特殊的约束或限制？（如时间、预算、技术限制）"
        else:
            return "[CLARIFICATION_DONE] 需求已澄清，准备开始辩论。"

    def _generate_debate_coordination(self, messages: Sequence[BaseChatMessage]) -> str:
        """生成辩论协调响应"""
        # 简化：记录状态
        return f"辩论进行中（第 {self._round_count} 轮）。\n共识点：{len(self._all_consensus)}\n分歧点：{len(self._all_disagreements)}"

    def _build_intervention_request(self) -> str:
        """构建用户介入请求"""
        points = self._all_disagreements[-3:] if self._all_disagreements else ["双方观点需要仲裁"]
        return build_intervention_prompt(points)

    def _generate_prd(self) -> str:
        """生成 PRD 内容"""
        consensus_text = "\n".join(f"- {item}" for item in self._all_consensus) or "暂无"
        disagreement_text = "\n".join(f"- {item}" for item in self._all_disagreements) or "暂无"

        return f"""# PRD: {self._topic or '产品需求文档'}

## 概述
{self._clarified_requirements or '待完善'}

## 功能需求

### 已达成共识的需求
{consensus_text}

### 待讨论/分歧点
{disagreement_text}

## 验收标准
待细化

## 实现建议
待细化

---
*本 PRD 由辩论系统生成*
*辩论轮数: {self._round_count}*
"""

    def get_final_prd(self) -> str:
        """获取最终 PRD 内容"""
        return self._generate_prd()

    def get_debate_summary(self) -> dict:
        """获取辩论摘要"""
        return {
            "total_rounds": self._round_count,
            "consensus_count": len(self._all_consensus),
            "disagreement_count": len(self._all_disagreements),
            "state": self._state.value,
        }