"""测试辩论系统核心功能"""

import asyncio
import os
import sys

# 添加src路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from debate_prd.core.debate_loop import run_debate_stream
from debate_prd.config.settings import LLMConfig, Settings


async def test_debate():
    """测试辩论流程"""
    # 加载API配置
    api_key = os.environ.get("OPENAI_API_KEY", "")
    base_url = os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

    if not api_key:
        print("错误: 未配置API Key")
        return

    print(f"使用模型: {model}")
    print(f"API地址: {base_url}")
    print("-" * 40)

    # 创建OpenAI兼容客户端
    from openai import AsyncOpenAI
    client = AsyncOpenAI(api_key=api_key, base_url=base_url)
    client.model = model

    # 辩论参数
    topic = "开发一个简单的用户登录功能"
    preset = "pm_vs_dev"
    settings = Settings(max_rounds=4)  # 测试时限制轮数

    print(f"议题: {topic}")
    print(f"预设: {preset}")
    print(f"最大轮数: {settings.max_rounds}")
    print("-" * 40)
    print("开始辩论...")
    print("=" * 40)

    # 运行辩论
    try:
        stream = run_debate_stream(
            topic=topic,
            llm_client=client,
            preset=preset,
            settings=settings,
        )

        round_num = 0

        async for event in stream:
            event_type = event.get("type", "")

            if event_type == "debate_start":
                print(f"[开始] 议题: {event['topic']}")

            elif event_type == "message":
                speaker = event["speaker"]
                role = event["role"]
                content = event["content"]

                # 更新轮数
                if "debater" in speaker.lower():
                    round_num += 1

                # 显示消息（截取前200字）
                display = content[:200] + "..." if len(content) > 200 else content
                print(f"\n[{round_num}] {role} ({speaker}):")
                print(display)

            elif event_type == "debate_complete":
                print("\n" + "=" * 40)
                print(f"[完成] 总轮数: {event['rounds']}")
                print(f"[原因] {event['reason']}")
                print("\n生成的PRD:")
                print("-" * 40)
                print(event["prd"])

    except Exception as e:
        print(f"\n错误: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    asyncio.run(test_debate())