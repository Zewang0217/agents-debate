"""基础辩论示例 - 展示自定义 LLM 配置"""

import asyncio
import os

from autogen_ext.models.openai import OpenAIChatCompletionClient

from debate_prd.config.presets import get_preset
from debate_prd.config.settings import Settings, LLMConfig
from debate_prd.team.debate_team import DebateTeam
from debate_prd.output.prd_generator import PRDGenerator


async def main():
    """运行基础辩论示例"""
    # ========== LLM 配置示例 ==========

    # 方式1: 使用环境变量 (推荐)
    # export OPENAI_API_KEY=your_key
    # export OPENAI_BASE_URL=https://api.deepseek.com/v1  # 可选
    # export OPENAI_MODEL=deepseek-chat                    # 可选
    llm_config = LLMConfig.from_env()

    # 方式2: 直接指定参数
    # llm_config = LLMConfig(
    #     api_key="your_api_key",
    #     base_url="https://api.deepseek.com/v1",  # 使用 DeepSeek
    #     model="deepseek-chat",
    # )

    # 方式3: 使用本地模型 (如 Ollama)
    # llm_config = LLMConfig(
    #     api_key="ollama",  # Ollama 不需要真实 API Key
    #     base_url="http://localhost:11434/v1",
    #     model="llama3",
    # )

    # 验证配置
    if not llm_config.api_key:
        print("请设置 OPENAI_API_KEY 环境变量或在代码中配置")
        return

    print(f"使用模型: {llm_config.model}")
    print(f"API Base URL: {llm_config.base_url}")

    # 创建模型客户端
    model_client = OpenAIChatCompletionClient(**llm_config.to_client_kwargs())

    # 选择预设
    preset_name = "pm_vs_dev"
    preset = get_preset(preset_name)

    print(f"\n预设角色: {preset['description']}")
    print(f"  Debater1: {preset['debater1']['role']} - {preset['debater1']['stance']}")
    print(f"  Debater2: {preset['debater2']['role']} - {preset['debater2']['stance']}")

    # 输入议题
    topic = """
    开发一个用户认证系统：
    - 支持手机号登录
    - 支持邮箱登录
    - 需要考虑安全性
    - 需要考虑用户体验
    """

    print(f"\n辩论议题: {topic.strip()}")

    # 创建团队
    settings = Settings(
        llm=llm_config,
        max_rounds=6,
    )
    team = DebateTeam(
        preset=preset_name,
        model_client=model_client,
        settings=settings,
    )

    # 运行辩论
    print("\n开始辩论...\n")
    print("=" * 50)

    stream = team.run_stream(topic.strip())

    async for event in stream:
        if hasattr(event, "messages"):
            for msg in event.messages:
                speaker = getattr(msg, "source", "system")
                content = str(getattr(msg, "content", msg))
                print(f"\n[{speaker}]")
                print(content[:300] + "..." if len(content) > 300 else content)

    # 获取结果
    print("\n" + "=" * 50)
    print("辩论完成")

    prd = team._moderator.get_final_prd()
    print("\n生成的 PRD:")
    print("-" * 40)
    print(prd[:1000] + "..." if len(prd) > 1000 else prd)

    # 保存 PRD
    generator = PRDGenerator()
    filepath = generator.save_string(prd, preset_name, "用户认证系统")
    print(f"\nPRD 已保存到: {filepath}")


if __name__ == "__main__":
    asyncio.run(main())