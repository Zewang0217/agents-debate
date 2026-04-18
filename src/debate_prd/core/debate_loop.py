"""辩论循环控制 - Moderator Agent驱动

完整流程：
CLARIFICATION(Agent问答) → DEBATE → INTERVENTION → SYNTHESIS → COMPLETE

Moderator作为LLM Agent，通过function calling调用ask_user Tool动态问答。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import asyncio
import json
import re
import jieba

from .spawn.debater_agent import DebaterAgent, create_debater_pair
from .messaging.mailbox import get_message_router, reset_message_router
from .tools.ask_user import AskUserTool
from ..config.settings import Settings


def _clean_unicode(text: str) -> str:
    """清理无效 Unicode 字符（surrogate 等）

    Args:
        text: 输入文本

    Returns:
        清理后的文本
    """
    # 移除 surrogate 字符 (U+D800 到 U+DFFF)
    text = re.sub(r"[\ud800-\udfff]", "", text)
    # 移除其他无效控制字符
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    # 移除 Windows 换行符 \r
    text = text.replace("\r", "")
    return text


class ModeratorState(Enum):
    """中控状态机"""

    CLARIFICATION = "clarification"  # Agent驱动的澄清阶段
    PRD_QUESTIONING = "prd_questioning"  # PRD问答阶段
    DEBATE = "debate"  # 辩论阶段
    INTERVENTION = "intervention"  # 用户介入
    SYNTHESIS = "synthesis"  # PRD综合
    COMPLETE = "complete"  # 完成


@dataclass
class ClarificationState:
    """澄清状态"""

    messages: list = field(default_factory=list)  # 对话历史
    collected_info: dict = field(default_factory=dict)  # 收集的信息
    rounds: int = 0  # 问答轮数


@dataclass
class PRDQuestioningState:
    """PRD问答状态"""

    current_round: int = 0
    answers: dict = field(default_factory=dict)


@dataclass
class GuidanceState:
    """引导状态"""

    off_topic_count: int = 0


@dataclass
class DebateState:
    """辩论状态"""

    round_num: int = 0
    terminated: bool = False
    termination_reason: str = ""
    consensus_points: list[str] = field(default_factory=list)
    disagreement_points: list[str] = field(default_factory=list)
    prd_items: list[str] = field(default_factory=list)  # 提取的 [PRD_ITEM] 条目


class ClarificationModerator:
    """澄清主持人 - LLM Agent直接对话

    流程：
    1. 调用 LLM，生成问题文本
    2. 如果问题结尾是问号或包含[QUESTION]，发出 ask 事件，然后暂停
    3. CLI 处理用户输入，调用 submit_user_answer() 提交回答
    4. CLI 再次调用 continue_clarification() 继续生成
    5. 循环直到 [CLARIFICATION_DONE]
    """

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
        self._last_question: str = ""  # 上一个问题（用于提交回答时关联）
        self._topic: str = ""  # 辩论议题

    def submit_user_answer(self, answer: str):
        """提交用户回答

        Args:
            answer: 用户回答内容
        """
        # 清理无效字符
        answer = _clean_unicode(answer)

        # 添加用户回答到消息历史
        self._state.messages.append({"role": "user", "content": answer})
        self._state.rounds += 1
        self._state.collected_info[f"问答{self._state.rounds}"] = {
            "question": self._last_question,
            "answer": answer,
        }

    async def start_clarification(self, topic: str):
        """开始澄清阶段

        Yields:
            事件流，遇到 ask 时暂停
        """
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
        """继续澄清阶段（用户已提交回答后）

        Yields:
            事件流，遇到 ask 时暂停
        """
        async for event in self._generate_next():
            yield event

    async def _generate_next(self):
        """生成下一个问题或结论

        Yields:
            事件流，遇到 ask 时发出事件并暂停
        """
        # 清理消息历史中的无效字符
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

        # 调用LLM
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
        # 清理 LLM 返回的内容
        content = _clean_unicode(content)

        # 添加到消息历史
        self._state.messages.append({"role": "assistant", "content": content})

        # 检查是否澄清完成
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

        # 检查是否包含问题标记
        if (
            "[QUESTION]" in content
            or content.strip().endswith("？")
            or content.strip().endswith("?")
        ):
            # 提取问题
            question = content.replace("[QUESTION]", "").strip()
            self._last_question = question

            # 发出 ask 事件，暂停
            yield {
                "type": "ask",
                "question": question,
            }
            return

        # 如果不是问题也不是完成，直接输出并继续
        yield {
            "type": "moderator_message",
            "content": content,
        }
        # 继续生成下一个
        async for event in self._generate_next():
            yield event

    def _extract_prd_base(self, content: str) -> str:
        """从澄清完成消息中提取PRD基础版"""
        prd = content.replace("[CLARIFICATION_DONE]", "").strip()
        if not prd or len(prd) < 50:
            info = self._state.collected_info
            lines = ["# PRD基础版\n"]
            for key, value in info.items():
                lines.append(
                    f"## {key}\n问题: {value['question']}\n回答: {value['answer']}\n"
                )
            prd = "\n".join(lines)
        return prd

    async def _generate_prd_base_stream(self, topic: str):
        """流式生成PRD基础版

        Yields:
            token级事件流
        """
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
                    yield {
                        "type": "token",
                        "role": "Moderator",
                        "delta": token,
                    }
        except Exception as e:
            yield {"type": "error", "message": f"PRD生成失败: {e}"}
            return

        yield {
            "type": "prd_generated",
            "prd_base": full_prd,
        }


class DebateModerator:
    """辩论主持人 - 状态机驱动"""

    DEFAULT_PRD_QUESTIONS = [
        ("目标用户", "这个产品/功能的目标用户是谁？请描述用户画像。"),
        ("核心功能", "核心功能是什么？请列出最重要的3-5个功能点。"),
        ("解决问题", "这个产品主要解决什么问题？用户的痛点是什么？"),
        ("成功指标", "如何衡量这个功能的成功？有哪些关键指标？"),
        ("约束条件", "有什么特殊的约束或限制？（时间、预算、技术、合规）"),
    ]

    def __init__(
        self,
        debater1: DebaterAgent,
        debater2: DebaterAgent,
        llm_client=None,  # 新增：用于澄清阶段
        settings: Settings = None,
        ask_user_tool=None,
    ):
        self.debater1 = debater1
        self.debater2 = debater2
        self._llm_client = llm_client
        self.settings = settings or Settings()

        # 状态机
        self._state = ModeratorState.CLARIFICATION
        self._questioning_state = PRDQuestioningState()
        self._guidance_state = GuidanceState()
        self._debate_state = DebateState()

        # Tool机制
        self._ask_user_tool = ask_user_tool

        # ClarificationModerator
        self._clarification_moderator: Optional[ClarificationModerator] = None

        # PRD内容
        self._prd_base: str = ""
        self._topic: str = ""

        # 注册moderator邮箱
        self._mailbox = get_message_router().register_agent("moderator")

    async def run_full_debate_stream(self, topic: str):
        """完整流程流式输出

        Args:
            topic: 辩论议题

        Yields:
            事件流
        """
        self._topic = topic

        self._state = ModeratorState.CLARIFICATION

        self._clarification_moderator = ClarificationModerator(
            llm_client=self._llm_client,
            settings=self.settings,
        )

        async for event in self._clarification_moderator.start_clarification(topic):
            yield event
            if event.get("type") == "tool_call":
                # 遇到 tool_call，暂停，等待 CLI 处理后调用 resume_clarification()
                return
            if event.get("type") == "clarification_done":
                self._prd_base = event.get("prd_base", "")
                break

    async def resume_clarification(self):
        """继续澄清阶段（用户已提交回答后）

        Yields:
            事件流
        """
        async for event in self._clarification_moderator.continue_clarification():
            yield event
            if event.get("type") == "tool_call":
                return
            if event.get("type") == "clarification_done":
                self._prd_base = event.get("prd_base", "")
                # 澄清完成，开始辩论阶段
                async for debate_event in self._start_debate_phase():
                    yield debate_event
                return

    def submit_user_answer(self, answer: str):
        """提交用户回答（外部调用）

        Args:
            answer: 用户回答内容
        """
        if self._clarification_moderator:
            self._clarification_moderator.submit_user_answer(answer)

    async def _start_debate_phase(self):
        """开始辩论阶段"""
        # Phase 3: 辩论阶段
        yield {"type": "phase_start", "phase": "debate"}
        self._state = ModeratorState.DEBATE

        # Moderator 开场白
        yield {
            "type": "moderator",
            "action": "debate_start",
            "content": f"辩论开始，请双方基于立场发表观点。\n\nPRD 基础版：\n{self._prd_base[:500]}...",
        }

        # 运行带引导的辩论
        async for event in self._run_debate_autonomous_stream(
            self._topic, self._prd_base
        ):
            yield event

        # Moderator 总结
        yield {
            "type": "moderator",
            "action": "debate_end",
            "content": "辩论结束，开始综合双方观点生成 PRD。",
        }

        # Phase 4: 综合阶段
        yield {"type": "phase_start", "phase": "synthesis"}
        self._state = ModeratorState.SYNTHESIS

        prd = self._generate_final_prd(self._topic)

        yield {
            "type": "debate_complete",
            "prd": prd,
            "rounds": self._debate_state.round_num,
            "reason": self._debate_state.termination_reason,
        }

        self._state = ModeratorState.COMPLETE

    async def _run_debate_autonomous_stream(self, topic: str, prd_base: str = ""):
        """自由辩论模式 - 并发发表看法 + 自由反驳

        流程：
        1. 并发阶段：双方同时发表看法（asyncio.gather）
        2. 自由辩论：谁有消息谁反驳（不强制轮流）

        Args:
            topic: 辩论议题
            prd_base: PRD 基础版
        """
        recent_messages = []

        # === 阶段1：并发发表看法 ===
        yield {"type": "sub_phase", "phase": "publish_view"}

        # 使用队列收集事件，实现真正的并发输出
        event_queue = asyncio.Queue()
        completed_count = 0

        async def run_pm():
            async for event in self.debater1.publish_view(topic, prd_base):
                await event_queue.put(("pm", event))

        async def run_dev():
            async for event in self.debater2.publish_view(topic, prd_base):
                await event_queue.put(("dev", event))

        # 启动并发任务
        pm_task = asyncio.create_task(run_pm())
        dev_task = asyncio.create_task(run_dev())

        # 实时从队列取出事件并 yield
        while completed_count < 2:
            source, event = await event_queue.get()
            yield event

            if event.get("type") == "message_complete":
                completed_count += 1
                self._extract_prd_items(event["content"])
                self._debate_state.round_num += 1
                self._extract_points(event["content"])
                recent_messages.append(event["content"])

        # 等待任务完成
        await asyncio.gather(pm_task, dev_task)

        # === 阶段2：自由辩论 ===
        yield {"type": "sub_phase", "phase": "free_debate"}

        while not self._debate_state.terminated:
            if self._check_termination():
                break

            if self._detect_off_topic(recent_messages[-3:], topic):
                guidance = self._generate_guidance(
                    topic, recent_messages[-1] if recent_messages else ""
                )
                yield {
                    "type": "guidance",
                    "content": guidance,
                    "severity": "warning",
                }
                self._guidance_state.off_topic_count += 1

            responded = False
            for debater in [self.debater1, self.debater2]:
                messages = await debater._mailbox.get_messages()
                if messages:
                    opponent_msg = messages[-1].content
                    full_content = ""
                    async for event in debater.respond_stream(
                        topic, opponent_msg, prd_base
                    ):
                        yield event
                        if event.get("type") == "message_complete":
                            full_content = event["content"]

                    if full_content:
                        self._extract_prd_items(full_content)
                        self._debate_state.round_num += 1
                        self._extract_points(full_content)
                        recent_messages.append(full_content)
                        responded = True

            if not responded:
                await asyncio.sleep(0.5)

    def get_current_state(self) -> ModeratorState:
        """获取当前状态"""
        return self._state

    def get_pending_question(self) -> Optional[tuple[str, str]]:
        """获取当前待回答问题"""
        if self._state != ModeratorState.PRD_QUESTIONING:
            return None

        current_round = self._questioning_state.current_round
        if current_round >= len(self.DEFAULT_PRD_QUESTIONS):
            return None

        category, question = self.DEFAULT_PRD_QUESTIONS[current_round]
        return (category, question)

    def _get_next_speaker(self, current: DebaterAgent) -> DebaterAgent:
        """获取下一个发言者"""
        if current == self.debater1:
            return self.debater2
        else:
            return self.debater1

    def _check_termination(self) -> bool:
        """检查终止条件"""
        MIN_ROUNDS_BEFORE_CONSENSUS_CHECK = 3
        if self._debate_state.round_num < MIN_ROUNDS_BEFORE_CONSENSUS_CHECK:
            return False

        if self._debate_state.round_num >= self.settings.max_rounds:
            self._debate_state.terminated = True
            self._debate_state.termination_reason = "达到轮数上限"
            return True

        total = len(self._debate_state.consensus_points) + len(
            self._debate_state.disagreement_points
        )
        if total > 0:
            ratio = len(self._debate_state.consensus_points) / total
            if ratio >= self.settings.consensus_threshold:
                self._debate_state.terminated = True
                self._debate_state.termination_reason = "达成共识"
                return True

        return False

    def _extract_points(self, content: str) -> None:
        """从内容中提取共识点和分歧点（带去重）"""
        import re

        # 提取共识点（AGREE, CONSENSUS, PARTIAL_AGREE）- 去重
        agree_pattern = (
            r"\[AGREE:([^\]]+)\]|\[CONSENSUS:([^\]]+)\]|\[PARTIAL_AGREE:([^\]]+)\]"
        )
        matches = re.findall(agree_pattern, content)
        for match in matches:
            consensus_text = match[0] or match[1] or match[2]
            if consensus_text and consensus_text not in self._debate_state.consensus_points:
                self._debate_state.consensus_points.append(consensus_text)

        # 提取分歧点（DISAGREE）- 去重
        if "[DISAGREE:" in content:
            disagree_pattern = r"\[DISAGREE:([^\]]+)\]"
            matches = re.findall(disagree_pattern, content)
            for match in matches:
                if match and match not in self._debate_state.disagreement_points:
                    self._debate_state.disagreement_points.append(match)

        # 无明确标记时的 fallback：提取核心观点而非截断全文
        if not any(
            marker in content
            for marker in ["[AGREE", "[PARTIAL_AGREE", "[CONSENSUS", "[DISAGREE"]
        ):
            # 尝试提取"问题/反驳"标题行（而非整个段落）
            problem_pattern = r"###?\s*(问题\d|反驳点|挑战)[：:\s]*([^\n]+)"
            problem_matches = re.findall(problem_pattern, content)

            if problem_matches:
                for match in problem_matches:
                    point = f"{match[0]}: {match[1][:100]}"
                    if point not in self._debate_state.disagreement_points:
                        self._debate_state.disagreement_points.append(point)
            else:
                # 提取核心立场句（首段前80字，而非全文截断）
                first_para = content.split("\n\n")[0] if "\n\n" in content else content
                stance = first_para.strip()[:80]
                if stance and stance not in self._debate_state.disagreement_points:
                    self._debate_state.disagreement_points.append(stance)

    def _extract_prd_items(self, content: str) -> list[str]:
        """从内容中提取 [PRD_ITEM] 条目（带去重）

        Args:
            content: 发言内容

        Returns:
            提取的新PRD条目列表（去重后）
        """
        import re

        pattern = r"\[PRD_ITEM\]\s*([^\n]+)"
        items = re.findall(pattern, content)

        new_items = []
        for item in items:
            if item not in self._debate_state.prd_items:
                self._debate_state.prd_items.append(item)
                new_items.append(item)

        return new_items

    def _detect_off_topic(self, recent_msgs: list[str], topic: str) -> bool:
        """偏题检测"""
        if len(recent_msgs) < 2:
            return False

        # 关键词重叠检测
        topic_keywords = set(self._extract_keywords(topic))

        for msg in recent_msgs:
            msg_keywords = set(self._extract_keywords(msg))
            overlap = len(topic_keywords & msg_keywords)

            # 关键词重叠低于30%视为偏题
            if len(topic_keywords) > 0 and overlap < len(topic_keywords) * 0.3:
                return True

        return False

    def _extract_keywords(self, text: str) -> list[str]:
        """提取关键词"""
        # 使用jieba分词
        words = jieba.cut(text)
        # 过滤短词和停用词
        keywords = [
            w
            for w in words
            if len(w) > 1 and w not in ["的", "是", "有", "在", "和", "对", "为", "这"]
        ]
        return keywords[:20]  # 最多20个关键词

    def _generate_guidance(self, topic: str, off_topic_content: str) -> str:
        """生成引导消息"""
        core_features = self._questioning_state.answers.get("核心功能", "核心议题")

        return f"""[Moderator引导] 辩论似乎偏离了议题。

当前议题: {topic}
偏题内容摘要: {off_topic_content[:100]}...

建议回归以下核心讨论点:
{core_features}

请双方围绕议题继续讨论。
"""

    def _generate_prd_base(self) -> str:
        """从问答生成PRD基础版"""
        answers = self._questioning_state.answers

        return f"""# PRD基础版

## 目标用户
{answers.get("目标用户", "待补充")}

## 核心功能
{answers.get("核心功能", "待补充")}

## 解决的问题
{answers.get("解决问题", "待补充")}

## 成功指标
{answers.get("成功指标", "待补充")}

## 约束条件
{answers.get("约束条件", "无")}

---
*通过问答对话生成，将在辩论中完善*
"""

    def _generate_final_prd(self, topic: str) -> str:
        """生成最终PRD（优化格式）

        包含：精简概述 + 分类PRD条目 + 共识/分歧分析
        """
        # 去重后的共识和分歧
        unique_consensus = list(dict.fromkeys(self._debate_state.consensus_points))
        unique_disagreement = list(dict.fromkeys(self._debate_state.disagreement_points[-10:]))

        # PRD条目分类
        prd_items = getattr(self._debate_state, "prd_items", [])
        categorized_items = self._categorize_prd_items(prd_items)

        # 精简概述（只取PRD基础版的前300字）
        overview = self._prd_base[:300] if self._prd_base else "待完善"
        if len(self._prd_base or "") > 300:
            overview += "..."

        return f"""# PRD: {topic}

## 概述
{overview}

## PRD 条目（辩论提取）

{categorized_items}

## 达成的共识

{self._format_consensus(unique_consensus)}

## 待解决的分歧

{self._format_disagreement(unique_disagreement)}

## 实现建议

1. **平衡双方观点** - 在产品价值和技术可行性之间寻找平衡点
2. **分阶段实现** - MVP优先验证核心功能，后续迭代完善
3. **明确边界** - 确定功能边界，避免过度开发

---

*辩论轮数: {self._debate_state.round_num}* | *结束原因: {self._debate_state.termination_reason}* | *PRD条目数: {len(prd_items)}*
"""

    def _categorize_prd_items(self, items: list[str]) -> str:
        """分类PRD条目（产品/技术/运营）"""
        if not items:
            return "暂无"

        # 关键词分类
        product_keywords = ["用户", "目标", "功能", "体验", "需求", "价值", "MVP", "验证"]
        tech_keywords = ["技术", "性能", "加载", "架构", "实现", "兼容", "优化", "指标"]
        ops_keywords = ["运营", "推广", "数据", "留存", "增长", "商业化", "营收"]

        product_items = []
        tech_items = []
        ops_items = []
        other_items = []

        for item in items:
            item_lower = item.lower()
            if any(kw in item_lower for kw in product_keywords):
                product_items.append(item)
            elif any(kw in item_lower for kw in tech_keywords):
                tech_items.append(item)
            elif any(kw in item_lower for kw in ops_keywords):
                ops_items.append(item)
            else:
                other_items.append(item)

        # 格式化输出
        lines = []
        if product_items:
            lines.append("**产品相关:**")
            for item in product_items[:5]:
                lines.append(f"  - {item}")
        if tech_items:
            lines.append("**技术相关:**")
            for item in tech_items[:5]:
                lines.append(f"  - {item}")
        if ops_items:
            lines.append("**运营相关:**")
            for item in ops_items[:5]:
                lines.append(f"  - {item}")
        if other_items:
            lines.append("**其他:**")
            for item in other_items[:3]:
                lines.append(f"  - {item}")

        return "\n".join(lines) if lines else "暂无"

    def _format_consensus(self, points: list[str]) -> str:
        """格式化共识点（使用 ✅ 标记）"""
        if not points:
            return "暂无"
        return "\n".join(f"✅ {p[:100]}" for p in points[:6])

    def _format_disagreement(self, points: list[str]) -> str:
        """格式化分歧点（使用 ❌ 标记）"""
        if not points:
            return "暂无"
        return "\n".join(f"❌ {p[:100]}" for p in points[:6])


async def run_debate(
    topic: str,
    llm_client,
    preset: str = "pm_vs_dev",
    settings: Settings = None,
) -> str:
    """运行辩论的便捷函数"""
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

    # 运行完整流程
    prd = await moderator.run_debate(topic)
    return prd


# ========== 流式输出支持 ==========


async def run_debate_stream(
    topic: str,
    llm_client,
    preset: str = "pm_vs_dev",
    settings: Settings = None,
    ask_user_tool=None,
):
    """流式运行完整辩论流程

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
        llm_client=llm_client,
        settings=settings,
        ask_user_tool=ask_user_tool,
    )

    # 运行完整流程
    async for event in moderator.run_full_debate_stream(topic):
        yield event
