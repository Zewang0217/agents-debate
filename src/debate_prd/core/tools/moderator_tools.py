"""Moderator Tools - 中控主动干预工具

提供 Moderator 检测关键决策点和僵局时主动向用户询问的能力：
- ask_user_for_decision: 异步询问关键决策（技术栈、预算等）
- resolve_stalemate: 僵局时停止辩论并强制询问用户看法
- generate_insight: 生成行业大牛视角的专业见解
"""

from dataclasses import dataclass, field
from typing import Optional
import asyncio
import json
import re


@dataclass
class UserDecisionRequest:
    """用户决策请求"""

    question: str  # 询问的问题
    context: str = ""  # 决策背景说明
    options: list[str] = field(default_factory=list)  # 可选选项
    allow_skip: bool = True  # 是否允许跳过


@dataclass
class UserDecisionResponse:
    """用户决策回答"""

    answer: str  # 用户回答
    selected_option: int = -1  # 选择的选项索引
    skipped: bool = False  # 是否跳过


@dataclass
class ModeratorInsight:
    """中控见解"""

    topic: str  # 分歧议题
    industry_practice: str = ""  # 行业惯例
    pm_risks: list[str] = field(default_factory=list)  # PM方案风险
    dev_risks: list[str] = field(default_factory=list)  # Dev方案风险
    compromise: str = ""  # 折中方案
    recommendation: str = ""  # 建议倾向
    reason: str = ""  # 原因


class ModeratorTools:
    """Moderator 主动干预 Tools"""

    def __init__(self):
        self._pending_decision: Optional[UserDecisionRequest] = None
        self._decision_response: Optional[str] = None
        self._decision_event: asyncio.Event = asyncio.Event()

        self._stalemate_info: dict = {}  # 僵局信息
        self._stalemate_response: Optional[str] = None
        self._stalemate_event: asyncio.Event = asyncio.Event()

        self._insight_info: dict = {}  # 见解信息
        self._insight_response: Optional[dict] = None
        self._insight_event: asyncio.Event = asyncio.Event()

    def get_tools_schema(self) -> list[dict]:
        """返回所有 Tool Schema（供 LLM function calling）"""
        return [
            self._get_ask_decision_schema(),
            self._get_resolve_stalemate_schema(),
        ]

    def _get_ask_decision_schema(self) -> dict:
        """ask_user_for_decision Tool Schema"""
        return {
            "type": "function",
            "function": {
                "name": "ask_user_for_decision",
                "description": "当辩论涉及关键决策点（如技术栈、预算、时间约束等）时，异步询问用户偏好。用户可以回答或跳过。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "向用户询问的问题，如'技术栈倾向？React还是Vue？'",
                        },
                        "context": {
                            "type": "string",
                            "description": "决策背景说明，如'PM倾向React，Dev倾向Vue'",
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选选项列表（如['React', 'Vue', 'Angular']）",
                        },
                    },
                    "required": ["question"],
                },
            },
        }

    def _get_resolve_stalemate_schema(self) -> dict:
        """resolve_stalemate Tool Schema"""
        return {
            "type": "function",
            "function": {
                "name": "resolve_stalemate",
                "description": "当辩论陷入僵局（双方反复争论同一问题无进展）时，停止辩论并向用户询问看法以打破僵局。用户必须回答才能继续。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "disagreement_topic": {
                            "type": "string",
                            "description": "僵局议题，如'技术架构选择'",
                        },
                        "pm_position": {
                            "type": "string",
                            "description": "PM 的立场摘要",
                        },
                        "dev_position": {
                            "type": "string",
                            "description": "Dev 的立场摘要",
                        },
                    },
                    "required": ["disagreement_topic", "pm_position", "dev_position"],
                },
            },
        }

    # === ask_user_for_decision ===

    async def ask_user_for_decision(
        self,
        question: str,
        context: str = "",
        options: list[str] = None,
    ) -> UserDecisionResponse:
        """执行异步决策询问

        Args:
            question: 询问的问题
            context: 决策背景
            options: 可选选项

        Returns:
            用户决策回答
        """
        self._pending_decision = UserDecisionRequest(
            question=question,
            context=context,
            options=options or [],
            allow_skip=True,
        )
        self._decision_response = None
        self._decision_event.clear()

        # 等待用户回答（最长 60 秒）
        try:
            await asyncio.wait_for(self._decision_event.wait(), timeout=60.0)
        except asyncio.TimeoutError:
            # 超时视为跳过
            return UserDecisionResponse(answer="", skipped=True)

        response = self._decision_response or ""

        # 解析选项选择
        if options and response:
            try:
                idx = int(response)
                if 0 <= idx < len(options):
                    return UserDecisionResponse(
                        answer=options[idx],
                        selected_option=idx,
                        skipped=False,
                    )
            except ValueError:
                pass

        return UserDecisionResponse(answer=response, skipped=response == "")

    def get_pending_decision(self) -> Optional[UserDecisionRequest]:
        """获取待处理的决策请求"""
        return self._pending_decision

    def submit_decision_response(self, answer: str):
        """提交决策回答"""
        self._decision_response = answer
        self._decision_event.set()

    def is_waiting_decision(self) -> bool:
        """是否正在等待决策回答"""
        return not self._decision_event.is_set()

    # === resolve_stalemate ===

    async def resolve_stalemate(
        self,
        disagreement_topic: str,
        pm_position: str,
        dev_position: str,
    ) -> str:
        """执行僵局解决询问（强制回答）

        Args:
            disagreement_topic: 僵局议题
            pm_position: PM 立场
            dev_position: Dev 立场

        Returns:
            用户看法
        """
        self._stalemate_info = {
            "topic": disagreement_topic,
            "pm_position": pm_position,
            "dev_position": dev_position,
        }
        self._stalemate_response = None
        self._stalemate_event.clear()

        # 等待用户回答（最长 120 秒，强制回答）
        try:
            await asyncio.wait_for(self._stalemate_event.wait(), timeout=120.0)
        except asyncio.TimeoutError:
            return "用户未回应，请双方尝试折中方案"

        return self._stalemate_response or ""

    def get_stalemate_info(self) -> dict:
        """获取僵局信息"""
        return self._stalemate_info

    def submit_stalemate_response(self, answer: str):
        """提交僵局回答"""
        self._stalemate_response = answer
        self._stalemate_event.set()

    def is_waiting_stalemate(self) -> bool:
        """是否正在等待僵局回答"""
        return not self._stalemate_event.is_set()

    # === 状态清理 ===

    def clear(self):
        """清除所有状态"""
        self._pending_decision = None
        self._decision_response = None
        self._decision_event.clear()
        self._stalemate_info = {}
        self._stalemate_response = None
        self._stalemate_event.clear()
        self._insight_info = {}
        self._insight_response = None
        self._insight_event.clear()

    # === generate_insight ===

    async def generate_insight(
        self,
        topic: str,
        pm_position: str,
        dev_position: str,
        attempts: int,
        llm_client,
    ) -> ModeratorInsight:
        """生成中控见解（行业大牛视角）

        Args:
            topic: 分歧议题
            pm_position: PM 立场
            dev_position: Dev 立场
            attempts: 讨论次数
            llm_client: LLM 客户端

        Returns:
            ModeratorInsight 见解对象
        """
        from ..config.prompts import MODERATOR_INSIGHT_PROMPT

        self._insight_info = {
            "topic": topic,
            "pm_position": pm_position,
            "dev_position": dev_position,
            "attempts": attempts,
        }

        prompt = MODERATOR_INSIGHT_PROMPT.format(
            topic=topic,
            pm_position=pm_position[:200],
            dev_position=dev_position[:200],
            attempts=attempts,
        )

        try:
            response = await llm_client.chat.completions.create(
                model=llm_client.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            content = response.choices[0].message.content or ""
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                result = json.loads(json_match.group())
                insight = ModeratorInsight(
                    topic=topic,
                    industry_practice=result.get("industry_practice", ""),
                    pm_risks=result.get("pm_risks", []),
                    dev_risks=result.get("dev_risks", []),
                    compromise=result.get("compromise", ""),
                    recommendation=result.get("recommendation", ""),
                    reason=result.get("reason", ""),
                )
                self._insight_response = result
                return insight
        except Exception as e:
            print(f"[ModeratorTools] 见解生成出错: {e}")

        return ModeratorInsight(topic=topic)

    def get_insight_info(self) -> dict:
        """获取见解信息"""
        return self._insight_info

    def get_insight_response(self) -> Optional[dict]:
        """获取见解响应"""
        return self._insight_response

    def format_insight(self, insight: ModeratorInsight) -> str:
        """格式化见解为可读文本

        Args:
            insight: ModeratorInsight 对象

        Returns:
            格式化后的文本
        """
        lines = ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
        lines.append("💡 Moderator 专业见解")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        if insight.industry_practice:
            lines.append(f"📌 行业惯例：{insight.industry_practice}")

        if insight.pm_risks:
            lines.append("⚠️ PM 方案风险：")
            for risk in insight.pm_risks[:3]:
                lines.append(f"  - {risk}")

        if insight.dev_risks:
            lines.append("⚠️ Dev 方案风险：")
            for risk in insight.dev_risks[:3]:
                lines.append(f"  - {risk}")

        if insight.compromise:
            lines.append(f"🔄 折中方案：{insight.compromise}")

        if insight.recommendation and insight.reason:
            lines.append(f"🎯 建议倾向：{insight.recommendation}")
            lines.append(f"   原因：{insight.reason}")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return "\n".join(lines)
