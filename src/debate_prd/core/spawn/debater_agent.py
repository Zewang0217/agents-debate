"""DebaterAgent - 辩论者代理

核心功能：
1. 持有立场（stance）
2. 记忆系统（project scope）
3. 消息传递（发送/接收）
4. LLM调用（生成反驳）
"""

from dataclasses import dataclass
from typing import Optional
import asyncio
import json

from ..memory.agent_memory import (
    MemoryScope,
    load_agent_memory,
    save_agent_memory,
    build_memory_prompt,
)
from ..messaging.mailbox import (
    get_message_router,
    DebateMessage,
)


@dataclass
class DebaterConfig:
    """辩论者配置"""
    name: str              # 代理名称（debater1, debater2）
    role: str              # 角色（PM, Dev, UX, Security）
    stance: str            # 立场描述
    focus_areas: list[str] # 关注领域
    color: str             # 显示颜色


class DebaterAgent:
    """辩论者代理 - 基于Claude Code Agent设计模式"""

    def __init__(
        self,
        config: DebaterConfig,
        llm_client,  # OpenAI兼容客户端
        opponent_name: str,
        memory_scope: MemoryScope = "project",
    ):
        """初始化辩论者

        Args:
            config: 辩论者配置
            llm_client: LLM客户端（OpenAI兼容）
            opponent_name: 对方代理名称
            memory_scope: 记忆scope
        """
        self.config = config
        self.name = config.name
        self.role = config.role
        self.stance = config.stance
        self._llm_client = llm_client
        self._opponent = opponent_name
        self._memory_scope = memory_scope

        # 注册邮箱
        self._mailbox = get_message_router().register_agent(self.name)

        # 加载记忆
        self._memory_content = load_agent_memory(
            f"{self.name}_{self.role}",
            scope=memory_scope
        )

    async def start_debate(self, topic: str) -> str:
        """开始辩论 - 发送第一轮观点

        Args:
            topic: 辩论议题

        Returns:
            第一轮观点
        """
        # 构建system prompt（包含记忆）
        system_prompt = self._build_system_prompt()

        # 构建用户prompt
        user_prompt = f"""
议题: {topic}

请作为{self.role}，基于你的立场发表第一轮观点。

要求：
1. 明确陈述你的核心立场
2. 列出你认为最重要的{len(self.config.focus_areas)}个关注点
3. 对议题提出初步建议

记住：你将与{self._opponent}进行辩论，对方会反驳你的观点。
"""

        # 调用LLM
        response = await self._call_llm(system_prompt, user_prompt)

        # 发送给对方
        await self._send_to_opponent(response)

        # 保存记忆
        self._save_round_memory(topic, response, None)

        return response

    async def respond(self, topic: str, opponent_view: str) -> str:
        """回应对方观点

        Args:
            topic: 辩论议题
            opponent_view: 对方观点

        Returns:
            反驳观点
        """
        # 检查是否有新消息
        messages = await self._mailbox.get_messages()

        # 构建system prompt
        system_prompt = self._build_system_prompt()

        # 构建用户prompt
        user_prompt = f"""
议题: {topic}

对方（{self._opponent}）的观点：
{opponent_view}

请作为{self.role}，反驳对方的观点。

要求：
1. 指出对方观点的问题或盲点
2. 坚持你的立场，提供支持证据
3. 尝试寻找共识点或明确分歧
4. 如果对方观点合理，可以表示部分同意

输出格式：
- 反驳点：[你的反驳]
- 支持论据：[为什么你的立场是对的]
- 共识点：[如果有共识]
- 分歧点：[如果无法达成一致]
"""

        # 调用LLM
        response = await self._call_llm(system_prompt, user_prompt)

        # 发送给对方
        await self._send_to_opponent(response)

        # 保存记忆
        self._save_round_memory(topic, response, opponent_view)

        return response

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用LLM（OpenAI兼容API）"""
        # 构建messages
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        # 调用API（流式）
        try:
            response = await self._llm_client.chat.completions.create(
                model=self._llm_client.model,
                messages=messages,
                stream=False,
                temperature=0.7,
                max_tokens=1024,
            )
            return response.choices[0].message.content
        except Exception as e:
            # 降级：非流式调用
            print(f"[{self.name}] LLM调用出错: {e}")
            return f"[{self.role}]: 由于技术问题，无法生成观点。请稍后重试。"

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        # 基础身份
        base_prompt = f"""
你是{self.role}，一个专业的辩论者。

## 你的立场
{self.stance}

## 你关注的领域
{', '.join(self.config.focus_areas)}

## 辩论规则
1. 坚持你的立场，但尊重对方观点
2. 用逻辑和证据支持你的论点
3. 识别对方的盲点并提出反驳
4. 如果发现共识，明确表示同意
5. 如果分歧无法解决，标记[DISAGREE]
"""

        # 加入记忆
        memory_prompt = build_memory_prompt(
            f"{self.name}_{self.role}",
            scope=self._memory_scope,
            extra_guidelines=[
                "- Use past successful arguments as reference",
                "- Avoid repeating points that didn't work",
            ]
        )

        if self._memory_content:
            return f"{base_prompt}\n\n## 你的记忆\n{self._memory_content}\n\n{memory_prompt}"
        else:
            return f"{base_prompt}\n\n{memory_prompt}"

    async def _send_to_opponent(self, content: str) -> None:
        """发送消息给对方"""
        from ..messaging.mailbox import send_to_agent
        await send_to_agent(
            from_agent=self.name,
            to_agent=self._opponent,
            content=content,
            message_type="text"
        )

    def _save_round_memory(
        self,
        topic: str,
        my_view: str,
        opponent_view: str | None
    ) -> None:
        """保存本轮记忆"""
        agent_type = f"{self.name}_{self.role}"

        # 加载现有记忆
        existing_memory = self._memory_content

        # 新增内容
        new_section = f"""
## Round Memory

### Topic
{topic}

### My Argument
{my_view[:500]}...

### Opponent's View
{opponent_view[:500] if opponent_view else 'N/A'}...

---
"""
        # 合并记忆
        if existing_memory:
            updated_memory = existing_memory + "\n" + new_section
        else:
            updated_memory = f"# Agent Memory: {agent_type}\n\n{new_section}"

        # 保存
        save_agent_memory(agent_type, updated_memory, scope=self._memory_scope)
        self._memory_content = updated_memory

    def get_memory(self) -> str:
        """获取当前记忆"""
        return self._memory_content


def create_debater_pair(
    llm_client,
    preset_name: str = "pm_vs_dev",
    memory_scope: MemoryScope = "project",
) -> tuple[DebaterAgent, DebaterAgent]:
    """创建一对辩论者

    Args:
        llm_client: LLM客户端
        preset_name: 预设名称
        memory_scope: 记忆scope

    Returns:
        (debater1, debater2)
    """
    # 加载预设
    from ...config.presets import get_preset
    preset = get_preset(preset_name)

    # 创建配置
    config1 = DebaterConfig(
        name="debater1",
        role=preset["debater1"]["role"],
        stance=preset["debater1"]["stance"],
        focus_areas=preset["debater1"]["focus_areas"],
        color="blue",
    )

    config2 = DebaterConfig(
        name="debater2",
        role=preset["debater2"]["role"],
        stance=preset["debater2"]["stance"],
        focus_areas=preset["debater2"]["focus_areas"],
        color="yellow",
    )

    # 创建Agent
    debater1 = DebaterAgent(
        config=config1,
        llm_client=llm_client,
        opponent_name="debater2",
        memory_scope=memory_scope,
    )

    debater2 = DebaterAgent(
        config=config2,
        llm_client=llm_client,
        opponent_name="debater1",
        memory_scope=memory_scope,
    )

    return debater1, debater2