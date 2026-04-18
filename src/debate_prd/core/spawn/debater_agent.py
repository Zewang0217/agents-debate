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

    name: str  # 代理名称（debater1, debater2）
    role: str  # 角色（PM, Dev, UX, Security）
    stance: str  # 立场描述
    focus_areas: list[str]  # 关注领域
    color: str  # 显示颜色


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
            f"{self.name}_{self.role}", scope=memory_scope
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

    async def start_debate_stream(self, topic: str, prd_base: str = ""):
        """开始辩论 - 流式输出

        Args:
            topic: 辩论议题
            prd_base: PRD 基础版（从澄清阶段生成）

        Yields:
            Token级事件字典
        """
        system_prompt = self._build_system_prompt()

        # 构建用户prompt，包含PRD基础版
        prd_context = f"\n\n## PRD 基础版\n{prd_base}" if prd_base else ""
        user_prompt = f"""
议题: {topic}{prd_context}

请作为{self.role}，基于你的立场发表第一轮观点。

要求：
1. 明确陈述你的核心立场和关注点
2. 针对PRD基础版中的内容提出你的观点和建议
3. 输出至少1个 [PRD_ITEM] 条目
4. 开放对话：明确表示你愿意倾听对方观点并寻求共识

记住：你将与{self._opponent}进行建设性辩论，目标是推动PRD完善，不是打败对方。
"""

        full_content = ""
        async for delta in self._call_llm_stream(system_prompt, user_prompt):
            # 过滤 STREAM_END 标记
            if delta.startswith("[STREAM_END:"):
                continue
            full_content += delta
            yield {
                "type": "token",
                "speaker": self.name,
                "role": self.role,
                "delta": delta,
                "color": self.config.color,
            }

        # 发送给对方
        await self._send_to_opponent(full_content)
        self._save_round_memory(topic, full_content, None)

        # 发送消息完成事件
        yield {
            "type": "message_complete",
            "speaker": self.name,
            "role": self.role,
            "content": full_content,
        }

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

    async def respond_stream(self, topic: str, opponent_view: str, prd_base: str = ""):
        """回应对方观点 - 流式输出

        Args:
            topic: 辩论议题
            opponent_view: 对方观点
            prd_base: PRD 基础版（从澄清阶段生成）

        Yields:
            Token级事件字典
        """
        # 检查是否有新消息
        messages = await self._mailbox.get_messages()

        # 构建system prompt
        system_prompt = self._build_system_prompt()

        # 构建用户prompt，包含PRD基础版
        prd_context = f"\n\n## PRD 基础版\n{prd_base}" if prd_base else ""
        user_prompt = f"""
议题: {topic}{prd_context}

## 对方观点（{self._opponent}）
{opponent_view}

## 你的任务
作为{self.role}，你的目标不是打败对方，而是推动PRD完善。

请按以下步骤回应：

### 1. 分析对方观点的价值
- 对方观点中哪些是合理的？
- 哪些观点与你立场一致？
- 哪些观点虽然挑战你，但有事实依据？

### 2. 指出问题并提出改进建议
- 对方观点中哪些有问题或盲点？
- 用事实和逻辑指出问题（不是情绪化反驳）
- 提出具体的改进建议或替代方案

### 3. 寻求共识或妥协方案
- 如果对方观点合理，使用 [AGREE:具体内容] 表示同意
- 如果部分合理，使用 [PARTIAL_AGREE:同意部分+改进建议] 表示部分同意
- 如果分歧无法调和，使用 [DISAGREE:分歧点+折中建议] 标记分歧并提出折中方案

### 4. 输出PRD条目
输出至少1个 [PRD_ITEM] 条目，推动PRD完善

## 辩论风格
- 尖锐有力：用事实和逻辑支持观点，不留模糊空间
- 理性开放：捍卫立场，但对合理观点开放妥协
- 建设性导向：目标不是打败对方，而是产出高质量PRD
"""

        full_content = ""
        async for delta in self._call_llm_stream(system_prompt, user_prompt):
            # 过滤 STREAM_END 标记
            if delta.startswith("[STREAM_END:"):
                continue
            full_content += delta
            yield {
                "type": "token",
                "speaker": self.name,
                "role": self.role,
                "delta": delta,
                "color": self.config.color,
            }

        # 发送给对方
        await self._send_to_opponent(full_content)
        self._save_round_memory(topic, full_content, opponent_view)

        # 发送消息完成事件
        yield {
            "type": "message_complete",
            "speaker": self.name,
            "role": self.role,
            "content": full_content,
        }

    async def _check_and_respond_stream(self, topic: str, prd_base: str = ""):
        """检查mailbox并回复（自主模式）

        Yields:
            token级事件流（如果有消息）
        """
        messages = await self._mailbox.get_messages()

        if not messages:
            return

        opponent_msg = messages[-1].content

        async for event in self.respond_stream(topic, opponent_msg, prd_base):
            yield event

    async def _call_llm(self, system_prompt: str, user_prompt: str) -> str:
        """调用LLM（非流式）- 用于记忆保存等场景"""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._llm_client.model,
                messages=messages,
                stream=False,
                temperature=0.8,
                max_tokens=600,
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"[{self.name}] LLM调用出错: {e}")
            return f"[{self.role}]: 由于技术问题，无法生成观点。请稍后重试。"

    async def _call_llm_stream(self, system_prompt: str, user_prompt: str):
        """流式调用LLM - Token级输出

        Yields:
            每个 token，最后返回完整内容
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        try:
            stream = await self._llm_client.chat.completions.create(
                model=self._llm_client.model,
                messages=messages,
                stream=True,
                temperature=0.8,
                max_tokens=600,
            )

            full_content = ""
            async for chunk in stream:
                if chunk.choices and chunk.choices[0].delta.content:
                    delta = chunk.choices[0].delta.content
                    full_content += delta
                    yield delta

            # 异步生成器不能 return 值，改为 yield 一个特殊的结束标记
            yield f"\n[STREAM_END:{full_content}]"

        except Exception as e:
            yield f"[{self.role}]: LLM调用出错: {e}"

    def _build_system_prompt(self) -> str:
        """构建系统提示词"""
        # 基础身份
        base_prompt = f"""
你是{self.role}，一个专业的辩论者。

## 你的立场
{self.stance}

## 你关注的领域
{", ".join(self.config.focus_areas)}

## 辩论规则
1. 捍卫立场但开放妥协：坚持核心立场，但对合理观点开放部分同意
2. 用事实说话：用逻辑、数据、案例支持观点，避免抽象争论
3. 建设性反驳：指出问题时同时提出改进建议或替代方案
4. 寻求共识优先：优先寻找双方一致点，使用 [AGREE] 或 [PARTIAL_AGREE] 标记
5. 分歧时提出折中：无法达成一致时，提出折中方案而非坚持对立
6. 目标导向：辩论目标是推动PRD完善，不是打败对方
"""

        # 加入记忆
        memory_prompt = build_memory_prompt(
            f"{self.name}_{self.role}",
            scope=self._memory_scope,
            extra_guidelines=[
                "- Use past successful arguments as reference",
                "- Avoid repeating points that didn't work",
            ],
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
            message_type="text",
        )

    def _save_round_memory(
        self, topic: str, my_view: str, opponent_view: str | None
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
{opponent_view[:500] if opponent_view else "N/A"}...

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
