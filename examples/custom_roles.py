"""自定义角色示例"""

import asyncio
import os

from autogen_ext.models.openai import OpenAIChatCompletionClient

from debate_prd.agents.debater import DebaterAgent
from debate_prd.agents.moderator import ModeratorAgent
from debate_prd.config.presets import DebaterConfig
from debate_prd.config.settings import Settings
from debate_prd.team.debate_team import DebateTeam


async def main():
    """运行自定义角色辩论示例"""
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("请设置 OPENAI_API_KEY 环境变量")
        return

    model_client = OpenAIChatCompletionClient(
        model="gpt-4o-mini",
        api_key=api_key,
    )

    # 自定义角色配置
    custom_config1: DebaterConfig = {
        "role": "创新者",
        "stance": "大胆尝试新想法，追求突破性创新",
        "focus_areas": [
            "颠覆性创新",
            "新技术应用",
            "市场差异化",
            "用户惊喜体验",
        ],
    }

    custom_config2: DebaterConfig = {
        "role": "保守派",
        "stance": "稳健务实，规避风险，追求可预期结果",
        "focus_areas": [
            "风险控制",
            "成本效益",
            "成熟技术",
            "渐进式改进",
        ],
    }

    print("自定义角色:")
    print(f"  Debater1: {custom_config1['role']} - {custom_config1['stance']}")
    print(f"  Debater2: {custom_config2['role']} - {custom_config2['stance']}")

    # 手动创建 Agents
    debater1 = DebaterAgent(
        name="debater1",
        model_client=model_client,
        config=custom_config1,
        opponent_role=custom_config2["role"],
    )

    debater2 = DebaterAgent(
        name="debater2",
        model_client=model_client,
        config=custom_config2,
        opponent_role=custom_config1["role"],
    )

    moderator = ModeratorAgent(
        name="moderator",
        model_client=model_client,
        settings=Settings(max_rounds=5),
    )

    print("\n提示: 自定义角色需要手动组装 DebateTeam")
    print("完整示例请参考 debate_prd/team/debate_team.py")


if __name__ == "__main__":
    asyncio.run(main())