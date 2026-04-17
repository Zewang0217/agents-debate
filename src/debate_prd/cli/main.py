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
  # 使用环境变量配置
  export OPENAI_API_KEY=your_key
  export OPENAI_BASE_URL=https://api.deepseek.com/v1
  export OPENAI_MODEL=deepseek-chat
  debate-prd

  # 使用命令行参数配置
  debate-prd --base-url https://api.deepseek.com/v1 --model deepseek-chat --api-key your_key

  # 使用本地模型（如 Ollama）
  debate-prd --base-url http://localhost:11434/v1 --model llama3 --api-key ollama

环境变量:
  OPENAI_API_KEY  - API Key
  OPENAI_BASE_URL - API Base URL (默认: https://api.openai.com/v1)
  OPENAI_MODEL    - 模型名称 (默认: gpt-4o-mini)
        """,
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
        default=10,
        help="辩论最大轮数 (默认: 10)",
    )
    parser.add_argument(
        "--preset",
        type=str,
        choices=list_presets(),
        default=None,
        help="预设角色组合，不指定则交互选择",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="辩论议题，不指定则交互输入",
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

    print("=" * 60)
    print("辩论式 PRD 生成系统")
    print("=" * 60)
    print()

    # 验证 API Key
    if not args.api_key:
        print("错误: 未提供 API Key")
        print("请通过 --api-key 参数或 OPENAI_API_KEY 环境变量设置")
        sys.exit(1)

    # 显示 LLM 配置
    print("LLM 配置:")
    print(f"  Base URL: {args.base_url}")
    print(f"  Model: {args.model}")
    print(f"  Max Rounds: {args.max_rounds}")
    print()

    # 创建 LLM 配置
    llm_config = LLMConfig(
        api_key=args.api_key,
        base_url=args.base_url,
        model=args.model,
    )

    # 选择预设
    if args.preset:
        preset = args.preset
    else:
        preset = _select_preset()

    # 输入议题
    if args.topic:
        topic = args.topic
    else:
        topic = _input_topic()

    # 运行辩论
    asyncio.run(run_debate(llm_config, preset, topic, args.max_rounds, args.output_dir))


def _select_preset() -> str:
    """交互选择预设角色组合"""
    presets = list_presets()
    print("可选的角色预设:")
    for i, name in enumerate(presets, 1):
        print(f"  {i}. {name}")

    while True:
        try:
            choice = input("\n请选择预设编号 (默认 1): ").strip()
            if not choice:
                return presets[0]
            idx = int(choice) - 1
            if 0 <= idx < len(presets):
                return presets[idx]
            print("编号无效，请重新输入")
        except ValueError:
            print("请输入数字")


def _input_topic() -> str:
    """交互输入辩论议题"""
    print("\n请描述你想要开发的产品或功能需求:")
    print("(例如: 一个用户登录系统，支持手机号和邮箱登录)")
    topic = input("> ").strip()
    if not topic:
        topic = "一个通用的产品需求"
    return topic


async def run_debate(
    llm_config: LLMConfig,
    preset: str,
    topic: str,
    max_rounds: int,
    output_dir: str,
):
    """运行辩论流程

    Args:
        llm_config: LLM 配置
        preset: 预设角色组合
        topic: 辩论议题
        max_rounds: 最大辩论轮数
        output_dir: 输出目录
    """
    print(f"\n开始辩论: {preset}")
    print(f"议题: {topic}")
    print("-" * 40)

    # 创建模型客户端（支持自定义 base_url）
    client_kwargs = llm_config.to_client_kwargs()
    model_client = OpenAIChatCompletionClient(**client_kwargs)

    # 创建辩论团队
    settings = Settings(
        llm=llm_config,
        max_rounds=max_rounds,
        prd_output_dir=output_dir,
    )
    team = DebateTeam(
        preset=preset,
        model_client=model_client,
        settings=settings,
    )

    # 创建记录器
    recorder = DebateRecorder(output_dir=output_dir)
    recorder.set_metadata(preset, topic)

    # 运行辩论
    try:
        round_num = 0
        stream = team.run_stream(topic)

        async for event in stream:
            if hasattr(event, "messages"):
                for msg in event.messages:
                    speaker = msg.source if hasattr(msg, "source") else "system"
                    content = str(msg.content) if hasattr(msg, "content") else str(msg)

                    # 打印消息
                    print(f"\n[{speaker}]")
                    print(content[:500] + "..." if len(content) > 500 else content)

                    # 记录
                    role = _get_role_from_speaker(speaker, team)
                    recorder.record(round_num, speaker, role, content)

                    if "debater" in speaker.lower():
                        round_num += 1

        # 生成 PRD
        print("\n" + "=" * 60)
        print("辩论完成，生成 PRD...")

        prd_content = team._moderator.get_final_prd()

        # 保存 PRD
        generator = PRDGenerator(output_dir=output_dir)
        filepath = generator.save_string(prd_content, preset, topic)

        print(f"\nPRD 已保存: {filepath}")

        # 保存辩论记录
        record_path = recorder.export()
        print(f"辩论记录已保存: {record_path}")

        # 显示摘要
        summary = recorder.get_summary()
        print("\n辩论摘要:")
        print(f"  - 总轮数: {summary['max_round']}")
        print(f"  - 共识点: {summary['consensus_count']}")
        print(f"  - 仲裁请求: {summary['arbitration_requests']}")

    except Exception as e:
        print(f"\n辩论出错: {e}")
        raise


def _get_role_from_speaker(speaker: str, team: DebateTeam) -> str:
    """从发言者名称获取角色"""
    if "debater1" in speaker.lower():
        return team._preset["debater1"]["role"]
    elif "debater2" in speaker.lower():
        return team._preset["debater2"]["role"]
    elif "moderator" in speaker.lower():
        return "Moderator"
    return "Unknown"


if __name__ == "__main__":
    main()