"""辩论循环控制 - Moderator + 两个Debater互发消息

核心流程：
1. Moderator启动辩论
2. Debater1发言 → Debater2反驳 → Debater1回应 → ...
3. Moderator监控轮数和终止条件
4. Moderator生成PRD

参考Claude Code的team lead + teammate模式
"""

from dataclasses import dataclass, field
from typing import Optional
import asyncio

from .spawn.debater_agent import DebaterAgent, create_debater_pair
from .messaging.mailbox import get_message_router, reset_message_router, DebateMessage
from ..config.settings import Settings


@dataclass
class DebateState:
    """辩论状态"""
    round_num: int = 0
    consensus_points: list[str] = field(default_factory=list)
    disagreement_points: list[str] = field(default_factory=list)
    terminated: bool = False
    termination_reason: str = ""


class DebateModerator:
    """辩论主持人 - 控制辩论流程"""

    def __init__(
        self,
        debater1: DebaterAgent,
        debater2: DebaterAgent,
        settings: Settings = None,
    ):
        self.debater1 = debater1
        self.debater2 = debater2
        self.settings = settings or Settings()
        self._state = DebateState()

        # 注册moderator邮箱
        self._mailbox = get_message_router().register_agent("moderator")

    async def run_debate(self, topic: str) -> str:
        """运行完整辩论流程

        Args:
            topic: 辩论议题

        Returns:
            生成的PRD内容
        """
        print(f"[Moderator] 开始辩论: {topic}")

        # 第一轮：debater1先发言
        view1 = await self.debater1.start_debate(topic)
        print(f"\n[{self.debater1.role}] {view1[:200]}...")
        self._state.round_num += 1

        # 辩论循环
        current_view = view1
        current_speaker = self.debater1

        while not self._state.terminated:
            # 检查终止条件
            if self._check_termination():
                break

            # 切换发言者
            next_speaker = self._get_next_speaker(current_speaker)

            # 反驳
            response = await next_speaker.respond(topic, current_view)
            print(f"\n[{next_speaker.role}] {response[:200]}...")

            # 更新状态
            self._state.round_num += 1
            self._extract_points(response)

            # 切换
            current_view = response
            current_speaker = next_speaker

            # 等待一小段时间（避免API限流）
            await asyncio.sleep(0.5)

        # 生成PRD
        prd = self._generate_prd(topic)
        print(f"\n[Moderator] 辩论结束，PRD已生成")

        return prd

    def _get_next_speaker(self, current: DebaterAgent) -> DebaterAgent:
        """获取下一个发言者"""
        if current == self.debater1:
            return self.debater2
        else:
            return self.debater1

    def _check_termination(self) -> bool:
        """检查终止条件"""
        # 轮数上限
        if self._state.round_num >= self.settings.max_rounds:
            self._state.terminated = True
            self._state.termination_reason = "达到轮数上限"
            return True

        # 共识比例
        total = len(self._state.consensus_points) + len(self._state.disagreement_points)
        if total > 0:
            ratio = len(self._state.consensus_points) / total
            if ratio >= self.settings.consensus_threshold:
                self._state.terminated = True
                self._state.termination_reason = "达成共识"
                return True

        return False

    def _extract_points(self, content: str) -> None:
        """从内容中提取共识点和分歧点"""
        # 记录所有观点作为分歧点（简化）
        self._state.disagreement_points.append(content[:150])

    def _generate_prd(self, topic: str) -> str:
        """生成PRD"""
        # 从辩论记录中提取关键观点
        all_views = "\n".join(self._state.disagreement_points[-8:])  # 取最近8轮

        return f"""# PRD: {topic}

## 概述
通过 {self.debater1.role} 与 {self.debater2.role} 的辩论，生成以下产品需求。

## 辩论核心观点

### {self.debater1.role} 立场
{self.debater1.stance}

### {self.debater2.role} 立场
{self.debater2.stance}

## 辩论摘要

{all_views if all_views else "辩论内容已记录"}

## 建议

1. **平衡双方观点** - 在产品价值和技术可行性之间寻找平衡点
2. **分阶段实现** - MVP优先验证核心功能，后续迭代完善
3. **明确边界** - 确定功能边界，避免过度开发

---

*辩论轮数: {self._state.round_num}*
*结束原因: {self._state.termination_reason}*
"""


async def run_debate(
    topic: str,
    llm_client,
    preset: str = "pm_vs_dev",
    settings: Settings = None,
) -> str:
    """运行辩论的便捷函数

    Args:
        topic: 辩论议题
        llm_client: LLM客户端
        preset: 预设名称
        settings: 配置

    Returns:
        PRD内容
    """
    # 重置消息路由器（新会话）
    reset_message_router()

    # 创建辩论者
    debater1, debater2 = create_debater_pair(
        llm_client=llm_client,
        preset_name=preset,
        memory_scope="project",
    )

    # 创建主持人
    moderator = DebateModerator(
        debater1=debater1,
        debater2=debater2,
        settings=settings,
    )

    # 运行辩论
    prd = await moderator.run_debate(topic)

    return prd


# ========== 流式输出支持 ==========

async def run_debate_stream(
    topic: str,
    llm_client,
    preset: str = "pm_vs_dev",
    settings: Settings = None,
):
    """流式运行辩论

    Yields:
        辩论消息事件
    """
    reset_message_router()

    debater1, debater2 = create_debater_pair(
        llm_client=llm_client,
        preset_name=preset,
        memory_scope="project",
    )

    moderator = DebateModerator(
        debater1=debater1,
        debater2=debater2,
        settings=settings,
    )

    # 发送开始事件
    yield {
        "type": "debate_start",
        "topic": topic,
        "preset": preset,
    }

    # 第一轮
    view1 = await debater1.start_debate(topic)
    yield {
        "type": "message",
        "speaker": debater1.name,
        "role": debater1.role,
        "content": view1,
    }

    moderator._state.round_num += 1

    # 辩论循环
    current_view = view1
    current_speaker = debater1

    while not moderator._state.terminated:
        if moderator._check_termination():
            break

        next_speaker = moderator._get_next_speaker(current_speaker)
        response = await next_speaker.respond(topic, current_view)

        yield {
            "type": "message",
            "speaker": next_speaker.name,
            "role": next_speaker.role,
            "content": response,
        }

        moderator._state.round_num += 1
        moderator._extract_points(response)

        current_view = response
        current_speaker = next_speaker

        await asyncio.sleep(0.5)

    # 发送结束事件
    prd = moderator._generate_prd(topic)
    yield {
        "type": "debate_complete",
        "prd": prd,
        "rounds": moderator._state.round_num,
        "reason": moderator._state.termination_reason,
    }