"""命令行入口"""

import argparse
import asyncio
import sys
import os

from autogen_ext.models.openai import OpenAIChatCompletionClient

from ..config.presets import list_presets
from ..config.settings import Settings, LLMConfig
from ..team.debate_team import DebateTeam
from ..output.prd_generator import PRDGenerator
from ..output.recorder import DebateRecorder


def parse_args() -> argparse.Namespace:
    """解析命令行参数"""
    parser = argparse.ArgumentParser(
        description="辩论式 PRD 生成系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # TUI模式（推荐，支持中文输入）
  debate-prd --tui --topic "开发用户登录系统" --preset pm_vs_dev

  # CLI模式（传统）
  debate-prd --topic "用户认证系统" --preset pm_vs_dev

  # 使用DeepSeek
  export OPENAI_API_KEY=your_key
  export OPENAI_BASE_URL=https://api.deepseek.com/v1
  export OPENAI_MODEL=deepseek-chat
  debate-prd --tui

  # 使用Ollama本地模型
  debate-prd --tui --base-url http://localhost:11434/v1 --model llama3 --api-key ollama

环境变量:
  OPENAI_API_KEY  - API Key
  OPENAI_BASE_URL - API Base URL (默认: https://api.openai.com/v1)
  OPENAI_MODEL    - 模型名称 (默认: gpt-4o-mini)
        """,
    )

    # 运行模式
    parser.add_argument(
        "--tui",
        action="store_true",
        help="启动TUI模式（支持中文输入，流式输出）",
    )

    # LLM 配置参数
    parser.add_argument(
        "--api-key",
        type=str,
        default=os.environ.get("OPENAI_API_KEY", ""),
        help="API Key (或设置 OPENAI_API_KEY 环境变量)",
    )
    parser.add_argument(
        "--base-url",
        type=str,
        default=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        help="API Base URL，支持任意兼容 OpenAI 格式的服务",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        help="模型名称",
    )
    parser.add_argument(
        "--max-rounds",
        type=int,
        default=6,
        help="辩论最大轮数 (默认: 6)",
    )
    parser.add_argument(
        "--preset",
        type=str,
        choices=list_presets(),
        default="pm_vs_dev",
        help="预设角色组合 (默认: pm_vs_dev)",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="辩论议题（TUI模式必须指定，支持中文）",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="./output",
        help="PRD 输出目录 (默认: ./output)",
    )

    return parser.parse_args()


def main():
    """命令行主入口"""
    args = parse_args()

    # TUI模式
    if args.tui:
        from .tui import run_tui
        run_tui(preset=args.preset, topic=args.topic)
        return

    # CLI模式
    print("=" * 60)
    print("辩论式 PRD 生成系统 (CLI模式)")
    print("=" * 60)
    print()

    # 验证 API Key
    if not args.api_key:
        print("错误: 未提供 API Key")
        print("请通过 --api-key 参数或 OPENAI_API_KEY 环境变量设置")
        sys.exit(1)

    # 显示配置
    print(f"模型: {args.model}")
    print(f"预设: {args.preset}")
    print()

    llm_config = LLMConfig(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
    )

    # 选择议题
    topic = args.topic or _input_topic()
    preset = args.preset

    asyncio.run(run_debate(llm_config, preset, topic, args.max_rounds, args.output_dir))


def _input_topic() -> str:
    """交互输入议题"""
    print("请输入辩论议题:")
    topic = input("> ").strip()
    return topic or "通用产品需求"


async def run_debate(
    llm_config: LLMConfig,
    preset: str,
    topic: str,
    max_rounds: int,
    output_dir: str,
):
    """运行辩论"""
    print(f"议题: {topic}")
    print("-" * 40)

    client_kwargs = llm_config.to_client_kwargs()
    model_client = OpenAIChatCompletionClient(**client_kwargs)

    settings = Settings(llm=llm_config, max_rounds=max_rounds)
    team = DebateTeam(preset=preset, model_client=model_client, settings=settings)

    recorder = DebateRecorder(output_dir=output_dir)
    recorder.set_metadata(preset, topic)

    try:
        round_num = 0
        stream = team.run_stream(topic)

        async for event in stream:
            if hasattr(event, "messages"):
                for msg in event.messages:
                    speaker = getattr(msg, 'source', 'system')
                    content = str(getattr(msg, 'content', msg))

                    print(f"\n[{speaker}]")
                    print(content[:500])

                    role = _get_role(speaker, team)
                    recorder.record(round_num, speaker, role, content)

                    if "debater" in speaker.lower():
                        round_num += 1

                    if "[PRD_COMPLETE]" in content:
                        prd = content.replace("[PRD_COMPLETE]", "").strip()
                        generator = PRDGenerator(output_dir=output_dir)
                        filepath = generator.save_string(prd, preset, topic)
                        print(f"\n◆ PRD已保存: {filepath}")
                        recorder.export()
                        return

    except Exception as e:
        print(f"\n错误: {e}")
        raise


def _get_role(speaker: str, team: DebateTeam) -> str:
    if "debater1" in speaker.lower():
        return team._preset["debater1"]["role"]
    elif "debater2" in speaker.lower():
        return team._preset["debater2"]["role"]
    return "Moderator"


if __name__ == "__main__":
    main()