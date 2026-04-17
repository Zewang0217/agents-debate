"""辩论 Agent：基于立场提出观点和反驳"""

from typing import Sequence

from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.base import Response
from autogen_agentchat.messages import TextMessage
from autogen_core.models import ChatCompletionClient

from ..config.presets import DebaterConfig
from ..config.prompts import build_debater_system_message


class DebaterAgent(AssistantAgent):
    """辩论 Agent

    基于预设立场提出观点，反驳对方，支持请求用户仲裁。

    特殊标记:
    - `[REQUEST_ARBITRATION]` - 请求用户仲裁
    - `[AGREE]` - 同意对方观点
    """

    def __init__(
        self,
        name: str,
        model_client: ChatCompletionClient,
        config: DebaterConfig,
        opponent_role: str,
    ):
        """初始化辩论 Agent

        Args:
            name: Agent 名称
            model_client: LLM 客户端
            config: 辩论角色配置
            opponent_role: 对方角色名称
        """
        super().__init__(
            name=name,
            model_client=model_client,
            system_message=build_debater_system_message(config, opponent_role),
        )
        self._role = config["role"]
        self._stance = config["stance"]
        self._focus_areas = config["focus_areas"]

    @property
    def role(self) -> str:
        """Agent 角色"""
        return self._role

    @property
    def stance(self) -> str:
        """Agent 立场"""
        return self._stance


def create_debater_pair(
    model_client: ChatCompletionClient,
    preset_name: str = "pm_vs_dev",
) -> tuple[DebaterAgent, DebaterAgent]:
    """创建一对辩论 Agent

    Args:
        model_client: LLM 客户端
        preset_name: 预设名称

    Returns:
        (debater1, debater2) 两个辩论 Agent
    """
    from ..config.presets import get_preset

    preset = get_preset(preset_name)

    debater1 = DebaterAgent(
        name="debater1",
        model_client=model_client,
        config=preset["debater1"],
        opponent_role=preset["debater2"]["role"],
    )

    debater2 = DebaterAgent(
        name="debater2",
        model_client=model_client,
        config=preset["debater2"],
        opponent_role=preset["debater1"]["role"],
    )

    return debater1, debater2