"""澄清主持人 - LLM Agent直接对话

从 debate_loop.py 拆分，负责澄清阶段：
- 多轮问答收集需求
- 生成PRD基础版
- 流式输出

流程：
1. 调用 LLM，生成问题文本
2. 如果问题结尾是问号或包含[QUESTION]，发出 ask 事件，然后暂停
3. CLI 处理用户输入，调用 submit_user_answer() 提交回答
4. CLI 再次调用 continue_clarification() 继续生成
5. 循环直到 [CLARIFICATION_DONE]
"""

import re
from .debate_state import ClarificationState
from .logger import get_logger
from ..config.settings import Settings

logger = get_logger("clarification")


def _clean_unicode(text: str) -> str:
    """清理无效 Unicode 字符"""
    text = re.sub(r"[\ud800-\udfff]", "", text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = text.replace("\r", "")
    return text


class ClarificationModerator:
    """澄清主持人 - LLM Agent直接对话"""

    CLARIFICATION_PROMPT = """你是Moderator（主持人），负责澄清用户需求，通过多轮对话收集信息后生成PRD基础版。

## 当前任务
用户提出了一个议题，你需要通过多轮对话澄清需求细节。

## 问答策略
1. 从宏观开始：先问目标用户、核心问题
2. 逐步深入：根据回答追问细节
3. 每次只问一个问题，等待用户回答后再继续
4. 适时总结：当收集足够信息后，输出[CLARIFICATION_DONE]并附带PRD基础版

## 特殊意图识别
**重要**：识别用户意图，主动响应：
- 如果用户表达"跳过"、"直接开始"、"不用澄清"、"快速开始辩论"、"skip"等意图
- 或用户表示"已经清楚了"、"需求明确"、"我知道要做什么"等自信表达
- 立即输出[CLARIFICATION_DONE]并附上简短的PRD概要（基于议题关键词推断）

示例用户表达：
- "跳过澄清阶段，直接开始辩论"
- "不用问了，直接开始"
- "需求很清楚，开始辩论吧"
- "skip"
- "我已经知道要做什么了"

响应方式：
[CLARIFICATION_DONE]
# PRD概要
基于议题"{议题关键词}"快速启动辩论，具体细节将在辩论中完善。

## 语言风格
简洁直接，不废话

## 输出标记
- [QUESTION] - 表示需要用户回答
- [CLARIFICATION_DONE] - 澄清完成，附带PRD基础版摘要
"""

    def __init__(self, llm_client, settings: Settings = None):
        self._llm_client = llm_client
        self._settings = settings or Settings()
        self._state = ClarificationState()
        self._last_question: str = ""
        self._topic: str = ""

    def submit_user_answer(self, answer: str):
        """提交用户回答"""
        answer = _clean_unicode(answer)
        self._state.messages.append({"role": "user", "content": answer})
        self._state.rounds += 1
        self._state.collected_info[f"问答{self._state.rounds}"] = {
            "question": self._last_question,
            "answer": answer,
        }

    async def start_clarification(self, topic: str):
        """开始澄清阶段"""
        self._topic = topic
        self._state.messages = [
            {"role": "system", "content": self.CLARIFICATION_PROMPT},
            {
                "role": "user",
                "content": f"议题: {topic}\n请开始澄清需求，每次只问一个问题。",
            },
        ]
        yield {"type": "phase_start", "phase": "clarification", "topic": topic}
        async for event in self._generate_next():
            yield event

    async def continue_clarification(self):
        """继续澄清阶段"""
        async for event in self._generate_next():
            yield event

    async def _generate_next(self):
        """生成下一个问题或结论"""
        cleaned_messages = []
        for msg in self._state.messages:
            cleaned_msg = {
                "role": msg["role"],
                "content": _clean_unicode(msg.get("content", ""))
                if msg.get("content")
                else None,
            }
            if msg.get("tool_calls"):
                cleaned_msg["tool_calls"] = msg["tool_calls"]
            if msg.get("tool_call_id"):
                cleaned_msg["tool_call_id"] = msg["tool_call_id"]
            cleaned_messages.append(cleaned_msg)

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._llm_client.model,
                messages=cleaned_messages,
                temperature=0.7,
            )
        except Exception as e:
            yield {"type": "error", "message": f"LLM调用失败: {e}"}
            return

        content = response.choices[0].message.content or ""
        content = _clean_unicode(content)
        self._state.messages.append({"role": "assistant", "content": content})

        if "[CLARIFICATION_DONE]" in content:
            yield {"type": "phase_start", "phase": "prd_generation"}
            full_prd = ""
            async for event in self._generate_prd_base_stream(topic=self._topic):
                yield event
                if event.get("type") == "prd_generated":
                    full_prd = event.get("prd_base", "")
            yield {
                "type": "clarification_done",
                "prd_base": full_prd,
                "rounds": self._state.rounds,
            }
            return

        if (
            "[QUESTION]" in content
            or content.strip().endswith("？")
            or content.strip().endswith("?")
        ):
            question = content.replace("[QUESTION]", "").strip()
            self._last_question = question
            yield {"type": "ask", "question": question}
            return

        yield {"type": "moderator_message", "content": content}
        async for event in self._generate_next():
            yield event

    async def _generate_prd_base_stream(self, topic: str):
        """流式生成PRD基础版"""
        system_prompt = """你是专业的产品经理，负责生成PRD基础版。

要求：
1. 基于用户澄清阶段的信息生成完整的PRD基础版
2. 包含：目标用户、核心功能、解决的问题、成功指标、约束条件
3. 使用Markdown格式，清晰结构化
4. 简洁精炼，控制在800字以内
"""
        collected_summary = "\n".join(
            [
                f"Q: {v['question']}\nA: {v['answer']}"
                for k, v in self._state.collected_info.items()
            ]
        )
        user_prompt = f"""
议题: {topic}

用户澄清信息:
{collected_summary}

请生成完整的PRD基础版。
"""
        full_prd = ""
        try:
            stream = await self._llm_client.chat.completions.create(
                model=self._llm_client.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                stream=True,
                temperature=0.7,
                max_tokens=800,
            )
            async for delta in stream:
                if delta.choices and delta.choices[0].delta.content:
                    token = delta.choices[0].delta.content
                    full_prd += token
                    yield {"type": "token", "role": "Moderator", "delta": token}
        except Exception as e:
            yield {"type": "error", "message": f"PRD生成失败: {e}"}
            return

        yield {"type": "prd_generated", "prd_base": full_prd}


__all__ = ["ClarificationModerator"]
