"""自定义终止条件"""

from typing import Sequence

from autogen_agentchat.base import TerminationCondition
from autogen_agentchat.messages import BaseChatMessage, TextMessage


class StalemateTermination(TerminationCondition):
    """僵局终止条件：连续多轮无实质进展"""

    def __init__(self, stalemate_rounds: int = 3):
        """初始化

        Args:
            stalemate_rounds: 僵局轮数阈值
        """
        self._stalemate_rounds = stalemate_rounds
        self._consecutive_stalemate = 0
        self._triggered = False

    @property
    def triggered(self) -> bool:
        return self._triggered

    async def __call__(self, messages: Sequence[BaseChatMessage]) -> bool:
        """检查是否触发僵局终止"""
        if self._triggered:
            return True

        # 检查是否有实质进展
        has_progress = self._check_progress(messages)

        if has_progress:
            self._consecutive_stalemate = 0
        else:
            self._consecutive_stalemate += 1

        if self._consecutive_stalemate >= self._stalemate_rounds:
            self._triggered = True
            return True

        return False

    def _check_progress(self, messages: Sequence[BaseChatMessage]) -> bool:
        """检查是否有实质进展"""
        for msg in messages[-2:]:
            content = str(msg.content)
            # 检查共识标记
            if "[AGREE]" in content or "[CONSENSUS]" in content:
                return True
            # 检查新观点（简化检测）
            if len(content) > 50 and "反驳" not in content[:20]:
                return True
        return False

    def reset(self) -> None:
        """重置状态"""
        self._consecutive_stalemate = 0
        self._triggered = False


class InterventionTermination(TerminationCondition):
    """用户介入终止条件：暂停 Agent 对话等待用户"""

    def __init__(self, intervention_keywords: list[str] = None):
        """初始化

        Args:
            intervention_keywords: 触发介入的关键词列表
        """
        self._keywords = intervention_keywords or ["仲裁", "[REQUEST_USER]", "[REQUEST_ARBITRATION]"]
        self._triggered = False

    @property
    def triggered(self) -> bool:
        return self._triggered

    async def __call__(self, messages: Sequence[BaseChatMessage]) -> bool:
        """检查是否触发用户介入"""
        if self._triggered:
            return True

        for msg in messages:
            content = str(msg.content)
            for keyword in self._keywords:
                if keyword in content:
                    self._triggered = True
                    return True

        return False

    def reset(self) -> None:
        """重置状态"""
        self._triggered = False