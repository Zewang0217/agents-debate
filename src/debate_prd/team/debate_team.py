"""辩论团队编排：SelectorGroupChat 生成发言顺序"""

from typing import Callable

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import (
    TextMentionTermination,
    MaxMessageTermination,
    HandoffTermination,
)
from autogen_agentchat.teams import SelectorGroupChat
from autogen_agentchat.messages import BaseChatMessage
from autogen_core.models import ChatCompletionClient

from ..agents.debater import DebaterAgent, create_debater_pair
from ..agents.moderator import ModeratorAgent, ModeratorState
from ..config.presets import get_preset, list_presets
from ..config.settings import Settings, DEFAULT_SETTINGS


class DebateTeam:
    """辩论团队编排

    使用 SelectorGroupChat 动态选择发言者，
    包含两个辩论 Agent、一个中控 Agent、一个用户代理。
    """

    def __init__(
        self,
        preset: str = "pm_vs_dev",
        model_client: ChatCompletionClient = None,
        settings: Settings = None,
    ):
        """初始化辩论团队

        Args:
            preset: 预设角色组合名称
            model_client: LLM 客户端（必须）
            settings: 配置参数

        Raises:
            ValueError: 预设不存在或 model_client 为空
        """
        if model_client is None:
            raise ValueError("model_client 是必需参数")

        self._preset = get_preset(preset)
        self._settings = settings or DEFAULT_SETTINGS
        self._model_client = model_client

        # 创建 Agents
        self._debater1, self._debater2 = create_debater_pair(model_client, preset)
        self._moderator = ModeratorAgent(
            "moderator",
            model_client,
            self._settings,
        )

        # 创建终止条件
        self._termination = TextMentionTermination("[PRD_COMPLETE]") | MaxMessageTermination(
            self._settings.max_total_rounds * 4  # 每轮约 4 条消息
        )

        # 创建 SelectorGroupChat
        self._team = SelectorGroupChat(
            participants=[self._debater1, self._debater2, self._moderator],
            model_client=model_client,
            termination_condition=self._termination,
            selector_prompt=self._build_selector_prompt(),
        )

    def _build_selector_prompt(self) -> str:
        """构建发言者选择提示词"""
        return """你是一个辩论协调者，需要根据对话内容选择下一个发言的 Agent。

当前参与者：
- debater1 ({role}): {stance}
- debater2 ({role}): {stance}
- moderator: 中控 Agent，负责协调和记录

选择规则：
1. 如果是澄清阶段（moderator 正在引导），选择 moderator
2. 如果 moderator 刚发言邀请辩论，轮流选择 debater1 或 debater2
3. 如果一方刚反驳，另一方应该回应
4. 如果出现 [REQUEST_ARBITRATION]，等待 moderator 处理
5. 如果 moderator 判断需要用户介入，暂停 Agent 发言

请根据最近的消息内容，选择最合适的下一个发言者。
只返回 Agent 名称：debater1、debater2 或 moderator""".format(
            role=self._preset["debater1"]["role"],
            stance=self._preset["debater1"]["stance"],
        )

    async def run(self, topic: str = None):
        """运行辩论流程

        Args:
            topic: 辩论议题/需求描述

        Returns:
            PRD 内容字符串
        """
        # 初始任务
        initial_task = topic or "请描述你想要开发的产品或功能需求。"

        # 运行团队对话
        result = await self._team.run(task=initial_task)

        # 提取 PRD
        prd = self._moderator.get_final_prd()

        return prd

    async def run_stream(self, topic: str = None):
        """流式运行辩论流程

        Args:
            topic: 辩论议题/需求描述

        Yields:
            消息事件流
        """
        initial_task = topic or "请描述你想要开发的产品或功能需求。"

        stream = self._team.run_stream(task=initial_task)
        async for event in stream:
            yield event

    def get_debate_summary(self) -> dict:
        """获取辩论摘要"""
        return self._moderator.get_debate_summary()


def create_debate_team(
    preset: str = "pm_vs_dev",
    model_client: ChatCompletionClient = None,
    max_rounds: int = 10,
) -> DebateTeam:
    """创建辩论团队的便捷函数

    Args:
        preset: 预设角色组合
        model_client: LLM 客户端
        max_rounds: 最大辩论轮数

    Returns:
        DebateTeam 实例
    """
    settings = Settings(max_rounds=max_rounds)
    return DebateTeam(preset=preset, model_client=model_client, settings=settings)