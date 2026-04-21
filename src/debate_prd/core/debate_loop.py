"""辩论循环控制 - Moderator Agent驱动

完整流程：
CLARIFICATION(Agent问答) → DEBATE → INTERVENTION → SYNTHESIS → COMPLETE

Moderator作为LLM Agent，通过function calling调用ask_user Tool动态问答。

重构改进：
- 引入 DebateExecutor 执行辩论循环
- 引入 DebateAnalyzer 进行 LLM 分析
- 使用 logging 替代 print
- Guard Clause 减少嵌套
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
from .tools.moderator_tools import ModeratorTools
from .logger import get_logger
from ..config.settings import Settings
from ..config.prompts import (
    MODERATOR_ANALYSIS_PROMPT,
    MODERATOR_DEEP_ANALYSIS_PROMPT,
    MODERATOR_DEEP_ANALYSIS_PROMPT_V2,
    MODERATOR_INSIGHT_PROMPT,
)
from .prd_draft import PRDWorkingDraft, PRDItemExtended

logger = get_logger("loop")


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
class ConsensusPoint:
    """共识点"""

    content: str  # 共识内容描述
    category: str = ""  # 类别：技术/产品/商业/用户体验
    locked: bool = False  # 是否已锁定（不需要再讨论）
    evidence: list[str] = field(default_factory=list)  # 来源证据
    round_created: int = 0  # 创建轮次


@dataclass
class DisagreementPoint:
    """分歧点"""

    topic: str  # 分歧议题
    pm_position: str = ""  # PM 立场
    dev_position: str = ""  # Dev 立场
    priority: str = "normal"  # 优先级：high/normal/low
    category: str = ""  # 类别
    round_created: int = 0  # 创建轮次
    attempts: int = 0  # 讨论尝试次数（僵局检测）
    resolved: bool = False  # 是否已解决
    resolution: str = ""  # 解决方案


@dataclass
class PRDItem:
    """PRD 条目"""

    content: str  # 条目内容
    source: str = ""  # 来源：consensus/pm/dev/moderator
    status: str = "pending"  # 状态：pending/confirmed/disputed
    category: str = ""  # 类别


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
    """辩论状态 - 结构化共识/分歧"""

    round_num: int = 0
    terminated: bool = False
    termination_reason: str = ""

    # 新：结构化共识/分歧
    locked_consensus: list[ConsensusPoint] = field(default_factory=list)
    pending_consensus: list[ConsensusPoint] = field(default_factory=list)
    active_disagreements: list[DisagreementPoint] = field(default_factory=list)

    # 新：PRD 补充版
    prd_supplement: str = ""
    prd_items: list[PRDItem] = field(default_factory=list)

    # 新：辩论简要历史
    debate_summary: list[dict] = field(default_factory=list)
    # [{"round": 1, "pm_key_points": [...], "dev_key_points": [...]}]

    # 用户决策记录
    user_decisions: list[dict] = field(default_factory=list)

    # 保留：兼容旧字段（过渡期）
    agree_points: list[str] = field(default_factory=list)
    partial_agree_points: list[str] = field(default_factory=list)
    disagreement_points: list[str] = field(default_factory=list)
    consensus_points: list[str] = field(default_factory=list)
    stalemate_count: int = 0


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
        self._moderator_tools = ModeratorTools()  # 新增：中控主动干预工具

        # 已询问过的关键决策点（避免重复）
        self._asked_decisions: set[str] = set()

        # ClarificationModerator
        self._clarification_moderator: Optional[ClarificationModerator] = None

        # PRD内容
        self._prd_base: str = ""
        self._topic: str = ""
        self._prd_draft: Optional[PRDWorkingDraft] = None  # 新增：PRD工作草稿

        # 注册moderator邮箱
        self._mailbox = get_message_router().register_agent("moderator")

    async def _analyze_first_round(self, pm_content: str, dev_content: str) -> dict:
        """第一轮中控 LLM 分析

        Args:
            pm_content: PM 第一轮发言
            dev_content: Dev 第一轮发言

        Returns:
            分析结果字典
        """
        if not self._llm_client:
            return {}

        prompt = MODERATOR_ANALYSIS_PROMPT.format(
            prd_base=self._prd_base,
            pm_content=pm_content,
            dev_content=dev_content,
        )

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._llm_client.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            content = response.choices[0].message.content or ""
            # 提取 JSON（可能被 markdown 包裹）
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                result = json.loads(json_match.group())
            else:
                result = json.loads(content)

            # 更新 DebateState
            self._update_state_from_analysis(result, round_num=1)
            return result

        except Exception as e:
            logger.error(f"第一轮分析失败 error={e}")
            return {}

    def _update_state_from_analysis(self, analysis: dict, round_num: int):
        """根据 LLM 分析结果更新 DebateState

        Args:
            analysis: LLM 分析返回的 JSON
            round_num: 当前轮次
        """
        # 更新锁定共识
        for item in analysis.get("locked_consensus", []):
            point = ConsensusPoint(
                content=item.get("content", ""),
                category=item.get("category", ""),
                locked=True,
                evidence=item.get("evidence", []),
                round_created=round_num,
            )
            if point.content and point not in self._debate_state.locked_consensus:
                self._debate_state.locked_consensus.append(point)

        # 更新待定共识
        for item in analysis.get("pending_consensus", []):
            point = ConsensusPoint(
                content=item.get("content", ""),
                category=item.get("category", ""),
                locked=False,
                evidence=item.get("evidence", []),
                round_created=round_num,
            )
            if point.content and point not in self._debate_state.pending_consensus:
                self._debate_state.pending_consensus.append(point)

        # 更新分歧点
        for item in analysis.get("active_disagreements", []):
            disagreement = DisagreementPoint(
                topic=item.get("topic", ""),
                pm_position=item.get("pm_position", ""),
                dev_position=item.get("dev_position", ""),
                priority=item.get("priority", "normal"),
                category=item.get("category", ""),
                round_created=round_num,
                attempts=0,
            )
            if disagreement.topic:
                # 检查是否已存在相同分歧
                existing = self._find_disagreement(disagreement.topic)
                if existing:
                    existing.pm_position = disagreement.pm_position
                    existing.dev_position = disagreement.dev_position
                else:
                    self._debate_state.active_disagreements.append(disagreement)

        # 更新 PRD 补充版
        updates = analysis.get("prd_supplement_updates", [])
        if updates:
            self._debate_state.prd_supplement = "\n".join(updates)

        # 兼容旧字段
        for point in self._debate_state.locked_consensus:
            if point.content not in self._debate_state.agree_points:
                self._debate_state.agree_points.append(point.content)
        for point in self._debate_state.pending_consensus:
            if point.content not in self._debate_state.partial_agree_points:
                self._debate_state.partial_agree_points.append(point.content)

    def _find_disagreement(self, topic: str) -> Optional[DisagreementPoint]:
        """查找已存在的分歧点

        Args:
            topic: 分歧议题

        Returns:
            已存在的分歧点或 None
        """
        for d in self._debate_state.active_disagreements:
            if d.topic == topic or topic in d.topic or d.topic in topic:
                return d
        return None

    def _build_moderator_sync(self) -> str:
        """构建中控同步信息给 Debater（完整 PRD 状态）

        Returns:
            同步信息字符串
        """
        # 格式化已锁定共识
        locked_text = ""
        if self._debate_state.locked_consensus:
            locked_text = "### ✅ 已锁定共识（无需讨论，直接使用）\n"
            for p in self._debate_state.locked_consensus[-5:]:
                locked_text += f"- {p.content}\n"

        # 格式化待定共识
        pending_text = ""
        if self._debate_state.pending_consensus:
            pending_text = "### ◐ 待定共识（可完善细节）\n"
            for p in self._debate_state.pending_consensus[-3:]:
                pending_text += f"- {p.content}\n"

        # 格式化分歧点（重点）
        disagreements_text = self._format_disagreements()

        # 格式化 PRD 条目
        prd_items_text = ""
        if self._debate_state.prd_items:
            prd_items_text = "### 📝 已提取 PRD 条目\n"
            for item in self._debate_state.prd_items[-5:]:
                prd_items_text += f"- {item}\n"

        # 构建同步信息
        sync_info = f"""[中控同步 - 第 {self._debate_state.round_num} 轮]

## ⚠️ 议题提醒（必须遵守）
原始议题：{self._topic}
**禁止讨论与议题无关的内容。如有偏题，立即纠正。**

## 最新 PRD 状态

{locked_text}{pending_text}{prd_items_text}
### ❌ 当前分歧点（重点讨论）
{disagreements_text}

## 引导方向
请优先讨论分歧点，尝试提出折中方案。
- 如果分歧点已讨论充分，提出新的 PRD 条目
- 引用观点时从上方内容或对话历史中找依据，不要虚构

## 发言要求
[AGREE: xxx] - 你同意的观点（说明具体内容）
[PARTIAL_AGREE: xxx] - 部分同意（说明保留意见）
[DISAGREE: xxx] - 不同意（必须说明理由）
[PRD_ITEM] xxx - PRD 条目建议
"""
        return sync_info

    def _format_disagreements(self) -> str:
        """格式化分歧点列表

        Returns:
            格式化后的分歧点文本
        """
        if not self._debate_state.active_disagreements:
            return "暂无明确分歧点"

        lines = []
        for i, d in enumerate(self._debate_state.active_disagreements, 1):
            if d.resolved:
                continue
            priority_mark = (
                "[高优先]"
                if d.priority == "high"
                else "[中优先]"
                if d.priority == "normal"
                else "[低优先]"
            )
            lines.append(f"{i}. {priority_mark} {d.topic}")
            if d.pm_position:
                lines.append(f"   PM立场: {d.pm_position[:80]}")
            if d.dev_position:
                lines.append(f"   Dev立场: {d.dev_position[:80]}")
            lines.append(f"   讨论次数: {d.attempts}")

        return "\n".join(lines) if lines else "暂无明确分歧点"

    def _quick_analyze_round(self, pm_content: str, dev_content: str) -> dict:
        """快速分析 - 正则提取标记

        Args:
            pm_content: PM 本轮发言
            dev_content: Dev 本轮发言

        Returns:
            分析结果字典
        """
        result = {
            "new_agrees": [],
            "new_disagrees": [],
            "new_prd_items": [],
            "new_info": [],
            "new_constraints": [],
            "new_risks": [],
            "new_scenarios": [],
            "new_questions": [],
            "progress_detected": False,
        }

        # 提取标记（原有）
        agree_pattern = r"\[AGREE:([^\n\]]*(?:\][^\n\]]*)*)\]"
        disagree_pattern = r"\[DISAGREE:([^\n\]]*(?:\][^\n\]]*)*)\]"
        prd_pattern = r"\[PRD_ITEM\] ([^\n]+)"

        # 新增标记提取
        info_pattern = r"\[INFO\] ([^\n]+)"
        constraint_pattern = r"\[CONSTRAINT\] ([^\n]+)"
        risk_pattern = r"\[RISK\] ([^\n]+)"
        scenario_pattern = r"\[SCENARIO\] ([^\n]+)"
        question_pattern = r"\[QUESTION\] ([^\n]+)"

        for content in [pm_content, dev_content]:
            agrees = re.findall(agree_pattern, content, re.DOTALL)
            for match in agrees:
                point = match.strip()
                if point and point not in result["new_agrees"]:
                    result["new_agrees"].append(point)

            disagrees = re.findall(disagree_pattern, content, re.DOTALL)
            for match in disagrees:
                point = match.strip()
                if point and point not in result["new_disagrees"]:
                    result["new_disagrees"].append(point)

            prd_items = re.findall(prd_pattern, content)
            for item in prd_items:
                if item.strip() and item.strip() not in result["new_prd_items"]:
                    result["new_prd_items"].append(item.strip())

            # 新增标记提取
            info_items = re.findall(info_pattern, content)
            for item in info_items:
                if item.strip() and item.strip() not in result["new_info"]:
                    result["new_info"].append(item.strip())

            constraint_items = re.findall(constraint_pattern, content)
            for item in constraint_items:
                if item.strip() and item.strip() not in result["new_constraints"]:
                    result["new_constraints"].append(item.strip())

            risk_items = re.findall(risk_pattern, content)
            for item in risk_items:
                if item.strip() and item.strip() not in result["new_risks"]:
                    result["new_risks"].append(item.strip())

            scenario_items = re.findall(scenario_pattern, content)
            for item in scenario_items:
                if item.strip() and item.strip() not in result["new_scenarios"]:
                    result["new_scenarios"].append(item.strip())

            question_items = re.findall(question_pattern, content)
            for item in question_items:
                if item.strip() and item.strip() not in result["new_questions"]:
                    result["new_questions"].append(item.strip())

        # 检测是否有实质性推进
        progress_indicators = ["折中", "方案", "建议", "同意", "调整", "优化", "妥协"]
        for content in [pm_content, dev_content]:
            if any(indicator in content for indicator in progress_indicators):
                result["progress_detected"] = True
                break

        return result

    async def _deep_analyze_rounds(self, recent_rounds: int = 2) -> dict:
        """深度分析 - LLM 语义理解（每 2-3 轮调用）

        Args:
            recent_rounds: 分析最近几轮

        Returns:
            分析结果字典
        """
        if not self._llm_client or not self._debate_state.debate_summary:
            return {}

        # 获取最近的辩论记录
        recent = self._debate_state.debate_summary[-recent_rounds:]
        if not recent:
            return {}

        pm_recent = "\n".join(r.get("pm_key_points", "") for r in recent)
        dev_recent = "\n".join(r.get("dev_key_points", "") for r in recent)

        # 使用 V2 Prompt（行业大牛视角）
        prd_draft_summary = (
            self._prd_draft.get_summary() if self._prd_draft else "暂无草稿"
        )

        prompt = MODERATOR_DEEP_ANALYSIS_PROMPT_V2.format(
            prd_draft_summary=prd_draft_summary,
            round_start=recent[0].get("round", 1),
            round_end=recent[-1].get("round", self._debate_state.round_num),
            pm_recent_content=pm_recent[:1000],
            dev_recent_content=dev_recent[:1000],
        )

        try:
            response = await self._llm_client.chat.completions.create(
                model=self._llm_client.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
            )
            content = response.choices[0].message.content or ""
            json_match = re.search(r"\{[\s\S]*\}", content)
            if json_match:
                result = json.loads(json_match.group())
                self._apply_deep_analysis_result(result)
                return result
        except Exception as e:
            logger.error(f"深度分析失败 error={e}")

        return {}

    def _apply_deep_analysis_result(self, result: dict):
        """应用深度分析结果到状态

        Args:
            result: LLM 分析返回的 JSON
        """
        # 处理已解决的分歧
        for item in result.get("resolved_disagreements", []):
            topic = item.get("topic", "")
            disagreement = self._find_disagreement(topic)
            if disagreement:
                disagreement.resolved = True
                disagreement.resolution = item.get("resolution", "")
                if item.get("becomes_consensus"):
                    self._debate_state.locked_consensus.append(
                        ConsensusPoint(
                            content=disagreement.resolution,
                            category=disagreement.category,
                            locked=True,
                            round_created=self._debate_state.round_num,
                        )
                    )

        # 更新分歧状态
        for item in result.get("updated_disagreements", []):
            topic = item.get("topic", "")
            disagreement = self._find_disagreement(topic)
            if disagreement:
                if item.get("pm_position"):
                    disagreement.pm_position = item.get("pm_position")
                if item.get("dev_position"):
                    disagreement.dev_position = item.get("dev_position")
                disagreement.attempts = item.get("attempts", disagreement.attempts)

        # 添加新的锁定共识
        for content in result.get("new_locked_consensus", []):
            if content:
                point = ConsensusPoint(
                    content=content,
                    locked=True,
                    round_created=self._debate_state.round_num,
                )
                if point not in self._debate_state.locked_consensus:
                    self._debate_state.locked_consensus.append(point)

        # 更新 PRD 补充版
        for update in result.get("prd_updates", []):
            if update:
                # V2 格式：带 section/confidence
                if isinstance(update, dict):
                    section = update.get("section", "核心功能")
                    content = update.get("content", "")
                    source = update.get("source", "moderator")
                    confidence = update.get("confidence", "medium")
                    round_num = update.get("round", self._debate_state.round_num)

                    if content and self._prd_draft:
                        self._prd_draft.add_item(
                            section=section,
                            content=content,
                            source=source,
                            round_num=round_num,
                            confidence=confidence,
                        )

                    # 兼容旧格式：纯文本
                    if self._debate_state.prd_supplement:
                        self._debate_state.prd_supplement += f"\n{content}"
                    else:
                        self._debate_state.prd_supplement = content
                else:
                    # 兼容旧格式：纯字符串
                    if self._debate_state.prd_supplement:
                        self._debate_state.prd_supplement += f"\n{update}"
                    else:
                        self._debate_state.prd_supplement = update

    def _process_new_markers(self, quick_result: dict) -> None:
        """处理新增标记 - 添加到 PRD 草稿

        Args:
            quick_result: _quick_analyze_round 返回的结果
        """
        if not self._prd_draft:
            return

        round_num = self._debate_state.round_num

        # 处理 [INFO] 标记 -> 待定议题（信息补充）
        for info in quick_result.get("new_info", []):
            self._prd_draft.add_item(
                section="待定议题",
                content=f"[信息] {info}",
                source="debater",
                round_num=round_num,
                confidence="medium",
            )

        # 处理 [CONSTRAINT] 标记 -> 技术约束
        # 技术约束来自开发者，通常有技术依据，置信度较高
        for constraint in quick_result.get("new_constraints", []):
            self._prd_draft.add_item(
                section="技术约束",
                content=constraint,
                source="debater",
                round_num=round_num,
                confidence="high",
            )

        # 处理 [RISK] 标记 -> 风险点
        for risk in quick_result.get("new_risks", []):
            self._prd_draft.add_item(
                section="风险点",
                content=risk,
                source="debater",
                round_num=round_num,
                confidence="medium",
            )

        # 处理 [SCENARIO] 标记 -> 目标用户（场景补充）
        for scenario in quick_result.get("new_scenarios", []):
            self._prd_draft.add_item(
                section="目标用户",
                content=f"[场景] {scenario}",
                source="debater",
                round_num=round_num,
                confidence="medium",
            )

        # 处理 [QUESTION] 标记 -> 待定议题
        for question in quick_result.get("new_questions", []):
            self._prd_draft.add_item(
                section="待定议题",
                content=f"[待回答] {question}",
                source="debater",
                round_num=round_num,
                confidence="low",
            )

    async def _generate_moderator_insight(
        self,
        topic: str,
        pm_position: str,
        dev_position: str,
        attempts: int,
    ) -> dict:
        """生成中控见解（行业大牛视角）

        Args:
            topic: 分歧议题
            pm_position: PM 立场
            dev_position: Dev 立场
            attempts: 讨论次数

        Returns:
            见解 JSON
        """
        if not self._llm_client:
            return {}

        insight = await self._moderator_tools.generate_insight(
            topic=topic,
            pm_position=pm_position[:200],
            dev_position=dev_position[:200],
            attempts=attempts,
            llm_client=self._llm_client,
        )

        return self._moderator_tools.get_insight_response() or {}

    def _format_insight(self, insight: dict) -> str:
        """格式化见解为可读文本

        Args:
            insight: 见解 JSON

        Returns:
            格式化后的文本
        """
        from .tools.moderator_tools import ModeratorInsight

        insight_obj = ModeratorInsight(
            topic=self._topic,
            industry_practice=insight.get("industry_practice", ""),
            pm_risks=insight.get("pm_risks", []),
            dev_risks=insight.get("dev_risks", []),
            compromise=insight.get("compromise", ""),
            recommendation=insight.get("recommendation", ""),
            reason=insight.get("reason", ""),
        )

        return self._moderator_tools.format_insight(insight_obj)

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
        from .debate_executor import DebateExecutor

        yield {"type": "phase_start", "phase": "debate"}
        self._state = ModeratorState.DEBATE

        self._prd_draft = PRDWorkingDraft(topic=self._topic)

        yield {
            "type": "moderator",
            "action": "debate_start",
            "content": f"辩论开始，请双方基于立场发表观点。\n\nPRD 基础版：\n{self._prd_base}",
        }

        executor = DebateExecutor(self)
        async for event in executor.run_free_debate(self._topic, self._prd_base):
            yield event

        yield {
            "type": "moderator",
            "action": "debate_end",
            "content": "辩论结束，开始综合双方观点生成 PRD。",
        }

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
        logger.info(f"辩论阶段完成 rounds={self._debate_state.round_num}")

    async def _run_debate_autonomous_stream(self, topic: str, prd_base: str = ""):
        """自由辩论模式 - 通过 DebateExecutor 执行

        Args:
            topic: 辩论议题
            prd_base: PRD 基础版
        """
        from .debate_executor import DebateExecutor

        executor = DebateExecutor(self)
        async for event in executor.run_free_debate(topic, prd_base):
            yield event

    def submit_intervention(self, answer: str, category: str = None):
        """提交用户介入回答

        Args:
            answer: 用户回答
            category: 决策类别（可选）
        """
        self._pending_user_intervention = {
            "answer": answer,
            "category": category,
        }

    async def resume_debate(self):
        """恢复辩论（用户回答后）

        Yields:
            继续辩论的事件流
        """
        from .debate_executor import DebateExecutor

        executor = DebateExecutor(self)
        async for event in executor.continue_free_debate():
            yield event

    async def _continue_free_debate(self):
        """继续自由辩论（通过 DebateExecutor）"""
        from .debate_executor import DebateExecutor

        executor = DebateExecutor(self)
        async for event in executor.continue_free_debate():
            yield event

    def _generate_moderator_record(self, phase: str) -> dict:
        """生成 Moderator 记录事件"""
        agree_count = len(self._debate_state.agree_points)
        partial_count = len(self._debate_state.partial_agree_points)
        disagree_count = len(self._debate_state.disagreement_points)

        # 计算加权共识得分
        consensus_score = agree_count * 1.0 + partial_count * 0.5

        # 构建记录内容
        lines = [f"[{phase}] 共识进度"]

        if agree_count > 0:
            lines.append(f"  ✓ 完全共识({agree_count}):")
            for pt in self._debate_state.agree_points[-3:]:
                lines.append(f"    • {pt[:80]}")

        if partial_count > 0:
            lines.append(f"  ◐ 部分认同({partial_count}):")
            for pt in self._debate_state.partial_agree_points[-3:]:
                lines.append(f"    • {pt[:80]}")

        if disagree_count > 0:
            lines.append(f"  ✗ 待解决分歧({disagree_count}):")
            for pt in self._debate_state.disagreement_points[-3:]:
                lines.append(f"    • {pt[:80]}")

        lines.append(f"  📊 共识得分: {consensus_score:.1f}")

        return {
            "type": "moderator_record",
            "phase": phase,
            "content": "\n".join(lines),
            "agree_count": agree_count,
            "partial_count": partial_count,
            "disagree_count": disagree_count,
            "consensus_score": consensus_score,
        }

    def _generate_round_summary(self, analysis_result: dict = None) -> dict:
        """生成第一轮辩论总结事件

        Args:
            analysis_result: LLM 分析结果（可选）

        Returns:
            辩论总结事件字典
        """
        # 构建总结内容
        lines = ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
        lines.append("📊 第一轮辩论总结")
        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        # 锁定共识
        locked = self._debate_state.locked_consensus
        if locked:
            lines.append("")
            lines.append("✅ 已达成共识（锁定）")
            for point in locked:
                lines.append(f"• {point.content}")

        # 待定共识
        pending = self._debate_state.pending_consensus
        if pending:
            lines.append("")
            lines.append("◐ 基本共识（可完善）")
            for point in pending:
                lines.append(f"• {point.content}")

        # 分歧点
        disagreements = self._debate_state.active_disagreements
        if disagreements:
            lines.append("")
            lines.append("❌ 当前分歧点")
            for d in disagreements:
                priority_mark = "[高优先]" if d.priority == "high" else ""
                lines.append(f"• {priority_mark} {d.topic}")
                if d.pm_position or d.dev_position:
                    lines.append(f"  PM: {d.pm_position[:50]}")
                    lines.append(f"  Dev: {d.dev_position[:50]}")

        # PRD 补充
        prd_updates = self._debate_state.prd_supplement
        if prd_updates:
            lines.append("")
            lines.append("📝 PRD 补充更新")
            for line in prd_updates.split("\n"):
                if line.strip():
                    lines.append(f"• {line.strip()}")

        # 引导方向
        if analysis_result and analysis_result.get("guidance"):
            lines.append("")
            lines.append(f"🎯 下轮引导：{analysis_result.get('guidance')}")

        lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        return {
            "type": "round_summary",
            "round": 1,
            "content": "\n".join(lines),
            "locked_count": len(locked),
            "pending_count": len(pending),
            "disagreement_count": len(disagreements),
            "guidance": analysis_result.get("guidance", "") if analysis_result else "",
        }

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
        """检查终止条件 - 核心议题共识覆盖判定"""
        MIN_ROUNDS_BEFORE_TERMINATION = 4

        if self._debate_state.round_num < MIN_ROUNDS_BEFORE_TERMINATION:
            return False

        # 轮数上限兜底
        if self._debate_state.round_num >= self.settings.max_rounds:
            self._debate_state.terminated = True
            self._debate_state.termination_reason = "达到轮数上限"
            return True

        # 基于结构化状态的判断
        locked_count = len(self._debate_state.locked_consensus)
        pending_count = len(self._debate_state.pending_consensus)
        active_disagreements = [
            d for d in self._debate_state.active_disagreements if not d.resolved
        ]
        high_priority_disagreements = [
            d for d in active_disagreements if d.priority == "high"
        ]

        # 条件1: 所有高优先分歧已解决
        if locked_count >= 3 and len(high_priority_disagreements) == 0:
            self._debate_state.terminated = True
            self._debate_state.termination_reason = "核心分歧已解决"
            return True

        # 条件2: 共识覆盖度高（锁定共识数 >= 分歧数 * 2）
        if locked_count >= len(active_disagreements) * 2 and locked_count >= 3:
            self._debate_state.terminated = True
            self._debate_state.termination_reason = "共识覆盖充分"
            return True

        # 兼容旧逻辑：基于 agree_points 计算
        agree_count = len(self._debate_state.agree_points)
        partial_count = len(self._debate_state.partial_agree_points)
        disagree_count = len(self._debate_state.disagreement_points)

        consensus_score = agree_count * 1.0 + partial_count * 0.5
        total_points = agree_count + partial_count + disagree_count

        if total_points == 0:
            return False

        coverage_ratio = consensus_score / (total_points + 0.1)

        # 条件3: 高共识覆盖 (>70%)
        if coverage_ratio >= 0.7 and consensus_score >= 3:
            self._debate_state.terminated = True
            self._debate_state.termination_reason = "核心议题共识覆盖"
            return True

        # 条件4: 充分辩论（轮数足够+观点充分）
        if self._debate_state.round_num >= 6 and total_points >= 5:
            self._debate_state.terminated = True
            if disagree_count > agree_count:
                self._debate_state.termination_reason = "分歧为主-充分辩论"
            else:
                self._debate_state.termination_reason = "共识为主-充分辩论"
            return True

        # 条件5: 僵局（连续N轮观点无实质推进）
        if self._debate_state.stalemate_count >= 2:
            # 不直接终止，返回 False 让深度分析处理
            return False

        return False

    def _quick_check_termination(self) -> dict:
        """快速终止检查 - 不调 LLM

        Returns:
            终止判断结果
        """
        result = {
            "should_terminate": False,
            "reason": "",
        }

        # 轮数上限
        if self._debate_state.round_num >= self.settings.max_rounds:
            result["should_terminate"] = True
            result["reason"] = "达到轮数上限"
            return result

        # 检查高优先分歧僵局
        active_disagreements = [
            d for d in self._debate_state.active_disagreements if not d.resolved
        ]
        high_priority_disagreements = [
            d for d in active_disagreements if d.priority == "high"
        ]

        if (
            all(d.attempts >= 3 for d in high_priority_disagreements)
            and high_priority_disagreements
        ):
            # 触发用户干预，不直接终止
            result["should_terminate"] = False
            result["need_intervention"] = True
            result["intervention_type"] = "stalemate"
            result["disagreement"] = high_priority_disagreements[0]
            return result

        return result

    def _generate_stalemate_intervention(self, disagreement: DisagreementPoint) -> dict:
        """生成僵局干预事件

        Args:
            disagreement: 僵局的分歧点

        Returns:
            干预事件字典
        """
        return {
            "type": "stalemate_intervention",
            "topic": disagreement.topic,
            "pm_position": disagreement.pm_position,
            "dev_position": disagreement.dev_position,
            "attempts": disagreement.attempts,
            "question": f"双方在 [{disagreement.topic}] 上僵持 {disagreement.attempts} 轮，请给出你的倾向或决策：",
            "options": [
                "支持 PM 立场",
                "支持 Dev 立场",
                "折中方案",
                "暂时搁置",
            ],
            "allow_skip": False,  # 僵局必须回答
        }

    def _generate_critical_decision_intervention(
        self, disagreement: DisagreementPoint
    ) -> dict:
        """生成关键决策干预事件

        Args:
            disagreement: 关键分歧点

        Returns:
            干预事件字典
        """
        CRITICAL_CATEGORIES = ["技术栈", "架构", "预算", "时间约束", "核心功能取舍"]

        if disagreement.category not in CRITICAL_CATEGORIES:
            return None

        return {
            "type": "critical_decision_intervention",
            "topic": disagreement.topic,
            "category": disagreement.category,
            "pm_position": disagreement.pm_position,
            "dev_position": disagreement.dev_position,
            "question": f"关于 [{disagreement.category}] 的关键决策：{disagreement.topic}",
            "options": self._get_decision_options(disagreement.category),
            "allow_skip": True,  # 可以跳过
        }

    def _get_decision_options(self, category: str) -> list[str]:
        """根据类别获取决策选项

        Args:
            category: 决策类别

        Returns:
            选项列表
        """
        options_map = {
            "技术栈": ["React", "Vue", "Angular", "原生开发", "其他方案"],
            "架构": ["微服务", "单体应用", "混合架构", "暂缓决策"],
            "预算": ["充足投入", "保守预算", "分期投入", "暂缓决策"],
            "时间约束": ["快速上线", "稳健推进", "分阶段交付", "暂缓决策"],
            "核心功能取舍": ["保留核心", "简化范围", "分阶段实现", "暂缓决策"],
        }
        return options_map.get(category, ["支持 PM", "支持 Dev", "折中", "跳过"])

    async def _inject_user_decision(self, decision: str, topic: str):
        """注入用户决策到辩论流程

        Args:
            decision: 用户决策内容
            topic: 分歧议题
        """
        # 1. 记录决策
        self._debate_state.user_decisions.append(
            {
                "topic": topic,
                "decision": decision,
                "round": self._debate_state.round_num,
            }
        )

        # 2. 发送给双方 Agent mailbox
        from .messaging.mailbox import send_to_agent

        injection_msg = f"""[Moderator 补充信息]

用户针对 [{topic}] 做出决策：
{decision}

请基于此约束继续讨论，无需再争论此议题。
"""
        await send_to_agent("moderator", "debater1", injection_msg)
        await send_to_agent("moderator", "debater2", injection_msg)

        # 3. 更新分歧状态
        disagreement = self._find_disagreement(topic)
        if disagreement:
            disagreement.resolved = True
            disagreement.resolution = f"用户决策：{decision}"

            # 4. 转为锁定共识
            self._debate_state.locked_consensus.append(
                ConsensusPoint(
                    content=f"{topic}：{decision}",
                    category=disagreement.category,
                    locked=True,
                    evidence=["用户决策"],
                    round_created=self._debate_state.round_num,
                )
            )

            # 兼容旧字段
            self._debate_state.agree_points.append(f"{topic}：{decision}")

    def _is_viewpoint_progressed(self, full_content: str) -> bool:
        """判断观点是否有实质性推进

        推进定义:
        - 提出新论据/数据
        - 改变立场或妥协
        - 提出具体解决方案
        """
        progress_indicators = [
            "因此",
            "所以",
            "建议",
            "方案",
            "妥协",
            "同意",
            "我们可以",
            "具体做法",
            "提出",
            "方案如下",
            "折中",
            "调整",
            "改进",
            "优化",
        ]

        has_progress = any(
            indicator in full_content for indicator in progress_indicators
        )
        has_new_prd = "[PRD_ITEM]" in full_content

        return has_progress or has_new_prd

    def _extract_points(self, content: str, topic: str = "") -> None:
        """从内容中提取共识点和分歧点（带去重，区分类型，验证相关性）

        Args:
            content: 发言内容
            topic: 辩论议题（用于验证相关性）
        """
        import re

        # 清理流式标记 [STREAM_END:xxx] 或 [STREAM_END]
        content = re.sub(r"\[STREAM_END:[^\]]*\]", "", content)
        content = re.sub(r"\[STREAM_END\]", "", content)

        # 提取议题关键词（用于相关性验证）
        topic_keywords = set(self._extract_keywords(topic)) if topic else set()

        def _is_relevant_to_topic(point: str) -> bool:
            """验证共识点是否与议题相关"""
            if not topic_keywords:
                return True  # 无议题时默认接受
            point_keywords = set(self._extract_keywords(point))
            overlap = len(point_keywords & topic_keywords)
            # 关键词重叠 >= 20% 视为相关
            return overlap >= len(topic_keywords) * 0.2 or len(point_keywords) == 0

        # 改进正则：匹配完整内容（支持嵌套 ]）
        # 格式1: [AGREE:content] - 有具体内容，使用改进正则支持嵌套括号
        # 格式2: [AGREE] - 仅标记（提取上下文句）
        agree_pattern_with_content = r"\[AGREE:([^\n\]]*(?:\][^\n\]]*)*)\]"
        agree_pattern_no_content = r"\[AGREE\](?!\s*:)"
        consensus_pattern_with_content = r"\[CONSENSUS:([^\n\]]*(?:\][^\n\]]*)*)\]"
        consensus_pattern_no_content = r"\[CONSENSUS\](?!\s*:)"
        partial_agree_pattern_with_content = (
            r"\[PARTIAL_AGREE:([^\n\]]*(?:\][^\n\]]*)*)\]"
        )
        partial_agree_pattern_no_content = r"\[PARTIAL_AGREE\](?!\s*:)"

        # AGREE - 完全共识（有内容）
        agree_matches = re.findall(agree_pattern_with_content, content, re.DOTALL)
        for match in agree_matches:
            point = match.strip()
            if point and point not in self._debate_state.agree_points:
                # 验证相关性：只添加与议题相关的共识
                if _is_relevant_to_topic(point):
                    self._debate_state.agree_points.append(point)
                    if point not in self._debate_state.consensus_points:
                        self._debate_state.consensus_points.append(point)

        # AGREE - 完全共识（无内容时提取前后文）
        agree_no_content_matches = re.findall(agree_pattern_no_content, content)
        for _ in agree_no_content_matches:
            context_match = re.search(r"([^\n]{0,50})\[AGREE\]", content)
            if context_match:
                point = context_match.group(1).strip() or "同意"
                if point not in self._debate_state.agree_points:
                    # 验证相关性
                    if _is_relevant_to_topic(point):
                        self._debate_state.agree_points.append(point)
                        if point not in self._debate_state.consensus_points:
                            self._debate_state.consensus_points.append(point)

        # CONSENSUS - 完全共识（同AGREE处理）
        consensus_matches = re.findall(
            consensus_pattern_with_content, content, re.DOTALL
        )
        for match in consensus_matches:
            point = match.strip()
            if point and point not in self._debate_state.agree_points:
                # 验证相关性
                if _is_relevant_to_topic(point):
                    self._debate_state.agree_points.append(point)
                    if point not in self._debate_state.consensus_points:
                        self._debate_state.consensus_points.append(point)

        consensus_no_content_matches = re.findall(consensus_pattern_no_content, content)
        for _ in consensus_no_content_matches:
            context_match = re.search(r"([^\n]{0,50})\[CONSENSUS\]", content)
            if context_match:
                point = context_match.group(1).strip() or "共识"
                if point not in self._debate_state.agree_points:
                    # 验证相关性
                    if _is_relevant_to_topic(point):
                        self._debate_state.agree_points.append(point)
                        if point not in self._debate_state.consensus_points:
                            self._debate_state.consensus_points.append(point)

        # PARTIAL_AGREE - 部分共识（有内容）
        partial_matches = re.findall(
            partial_agree_pattern_with_content, content, re.DOTALL
        )
        for match in partial_matches:
            point = match.strip()
            if point and point not in self._debate_state.partial_agree_points:
                # 验证相关性
                if _is_relevant_to_topic(point):
                    self._debate_state.partial_agree_points.append(point)
                    if point not in self._debate_state.consensus_points:
                        self._debate_state.consensus_points.append(point)

        # PARTIAL_AGREE - 部分共识（无内容时提取前后文）
        partial_no_content_matches = re.findall(
            partial_agree_pattern_no_content, content
        )
        for _ in partial_no_content_matches:
            context_match = re.search(r"([^\n]{0,50})\[PARTIAL_AGREE\]", content)
            if context_match:
                point = context_match.group(1).strip() or "部分认同"
                if point not in self._debate_state.partial_agree_points:
                    # 验证相关性
                    if _is_relevant_to_topic(point):
                        self._debate_state.partial_agree_points.append(point)
                        if point not in self._debate_state.consensus_points:
                            self._debate_state.consensus_points.append(point)

        # 提取分歧点（DISAGREE）- 支持两种格式，改进正则支持嵌套括号
        disagree_pattern_with_content = r"\[DISAGREE:([^\n\]]*(?:\][^\n\]]*)*)\]"
        disagree_pattern_no_content = r"\[DISAGREE\](?!\s*:)"

        disagree_matches = re.findall(disagree_pattern_with_content, content, re.DOTALL)
        for match in disagree_matches:
            point = match.strip()
            if point and point not in self._debate_state.disagreement_points:
                self._debate_state.disagreement_points.append(point)

        disagree_no_content_matches = re.findall(disagree_pattern_no_content, content)
        for _ in disagree_no_content_matches:
            context_match = re.search(r"([^\n]{0,50})\[DISAGREE\]", content)
            if context_match:
                point = context_match.group(1).strip() or "分歧"
                if point not in self._debate_state.disagreement_points:
                    self._debate_state.disagreement_points.append(point)

        # Fallback：检查是否有任何匹配
        has_any_match = (
            agree_matches
            or agree_no_content_matches
            or consensus_matches
            or consensus_no_content_matches
            or partial_matches
            or partial_no_content_matches
            or disagree_matches
            or disagree_no_content_matches
        )

        if not has_any_match:
            problem_pattern = r"###?\s*(问题\d|反驳点|挑战)[：:\s]*([^\n]+)"
            problem_matches = re.findall(problem_pattern, content)

            if problem_matches:
                for match in problem_matches:
                    point = f"{match[0]}: {match[1][:100]}"
                    if point not in self._debate_state.disagreement_points:
                        self._debate_state.disagreement_points.append(point)
            else:
                first_para = content.split("\n\n")[0] if "\n\n" in content else content
                stance = first_para.strip()[:80]
                if stance and stance not in self._debate_state.disagreement_points:
                    self._debate_state.disagreement_points.append(stance)

    def _extract_prd_items(self, content: str) -> list[str]:
        """从内容中提取PRD条目（显式标记 + 智能提炼）

        Args:
            content: 发言内容

        Returns:
            提取的新PRD条目列表（去重后）
        """
        import re

        # 清理流式标记
        content = re.sub(r"\[STREAM_END:[^\]]*\]", "", content)
        content = re.sub(r"\[STREAM_END\]", "", content)

        # 1. 显式标记 [PRD_ITEM]
        explicit_pattern = r"\[PRD_ITEM\]\s*([^\n]+)"
        explicit_items = re.findall(explicit_pattern, content)

        # 2. 智能提炼：从关键词提取
        implicit_patterns = [
            r"建议[:：]\s*([^\n。]{10,50})",
            r"应该[:：]\s*([^\n。]{10,50})",
            r"需要[:：]\s*([^\n。]{10,50})",
            r"功能[:：]\s*([^\n。]{10,50})",
            r"实现[:：]\s*([^\n。]{10,50})",
            r"目标[:：]\s*([^\n。]{10,50})",
        ]

        implicit_items = []
        for pattern in implicit_patterns:
            matches = re.findall(pattern, content)
            implicit_items.extend(matches)

        # 合并去重
        all_items = explicit_items + implicit_items
        new_items = []
        for item in all_items:
            item_clean = item.strip()
            if item_clean and len(item_clean) >= 10:
                if item_clean not in self._debate_state.prd_items:
                    self._debate_state.prd_items.append(item_clean)
                    new_items.append(item_clean)

        return new_items

    def _detect_off_topic(self, recent_msgs: list[str], topic: str) -> dict:
        """偏题检测（返回检测结果和建议）

        Args:
            recent_msgs: 最近的消息列表
            topic: 辩论议题

        Returns:
            检测结果字典，包含：
            - is_off_topic: 是否偏题
            - hallucination: 是否幻觉引用
            - guidance: 纠正建议
        """
        result = {"is_off_topic": False, "hallucination": False, "guidance": ""}

        if len(recent_msgs) < 1:
            return result

        # 1. 关键词检测（保留现有逻辑）
        topic_keywords = set(self._extract_keywords(topic))

        for msg in recent_msgs:
            msg_keywords = set(self._extract_keywords(msg))
            overlap = len(topic_keywords & msg_keywords)

            # 关键词重叠低于30%视为偏题
            if len(topic_keywords) > 0 and overlap < len(topic_keywords) * 0.3:
                result["is_off_topic"] = True
                result["guidance"] = self._generate_guidance(topic, msg)
                return result

        # 2. 幻觉检测（新增）
        for msg in recent_msgs:
            hallucinated = self._detect_hallucinated_reference(msg, topic)
            if hallucinated:
                result["hallucination"] = True
                result["guidance"] = (
                    f"[警告] 你引用的观点「{hallucinated[:50]}」与议题无关，请核实后重新发言"
                )
                return result

        return result

    def _detect_hallucinated_reference(self, msg: str, topic: str) -> str | None:
        """检测是否引用与议题无关的内容（幻觉检测）

        检查 [AGREE: xxx] 或 [PARTIAL_AGREE: xxx] 或 "对方指出xxx" 等引用，
        如果引用内容的关键词与议题无重叠，可能是幻觉。

        Args:
            msg: 发言内容
            topic: 辩论议题

        Returns:
            如果检测到幻觉引用，返回引用内容；否则返回 None
        """
        # 匹配引用内容的正则
        patterns = [
            r"\[AGREE:\s*([^\]]+)\]",
            r"\[PARTIAL_AGREE:\s*([^\]]+)\]",
            r"对方.*指出[：:\s]*([^\n。]+)",
            r"对方.*说[：:\s]*([^\n。]+)",
            r"对方.*正确.*[：:\s]*([^\n。]+)",
        ]

        topic_keywords = set(self._extract_keywords(topic))

        for pattern in patterns:
            matches = re.findall(pattern, msg, re.DOTALL)
            for match in matches:
                referenced_content = match.strip()
                if len(referenced_content) < 5:
                    continue

                # 提取引用内容的关键词
                ref_keywords = set(self._extract_keywords(referenced_content))

                # 如果引用内容关键词与议题无重叠，可能是幻觉
                overlap = len(ref_keywords & topic_keywords)

                # 额外检查：如果引用内容包含明显不相关的关键词（如"游戏"、"H5"等）
                # 且议题中没有这些关键词，则视为幻觉
                unrelated_keywords = {
                    "游戏",
                    "H5",
                    "小程序",
                    "微信",
                    "手机",
                    "移动端",
                    "APP",
                    "应用",
                }
                topic_has_unrelated = any(
                    kw in topic_keywords for kw in unrelated_keywords
                )
                ref_has_unrelated = any(kw in ref_keywords for kw in unrelated_keywords)

                if ref_has_unrelated and not topic_has_unrelated:
                    return referenced_content

                # 如果关键词完全无重叠且引用内容有明确主题，视为幻觉
                if len(ref_keywords) > 0 and overlap == 0 and len(ref_keywords) >= 3:
                    return referenced_content

        return None

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

    def _detect_critical_decision(self, recent_messages: list[str]) -> Optional[dict]:
        """检测关键决策点

        当辩论涉及以下内容且双方存在分歧时，应询问用户：
        - 技术栈选择（React/Vue/Angular等）
        - 预算/成本约束
        - 时间约束（上线时间、开发周期）
        - 团队规模/人力
        - 架构方案（微服务/单体等）

        Returns:
            如果检测到关键决策点，返回决策信息；否则返回 None
        """
        CRITICAL_KEYWORDS = {
            "技术栈": ["技术栈", "框架", "React", "Vue", "Angular", "Next.js", "Nuxt"],
            "预算": ["预算", "成本", "费用", "投入", "资金"],
            "时间": ["时间", "周期", "上线", "交付", "deadline", "截止"],
            "团队": ["团队", "人力", "人员", "开发人员", "工程师"],
            "架构": ["架构", "微服务", "单体", "分布式", "单体应用"],
        }

        if len(recent_messages) < 2:
            return None

        # 检查最近消息中是否包含关键决策关键词
        recent_text = " ".join(recent_messages[-3:])

        for category, keywords in CRITICAL_KEYWORDS.items():
            for kw in keywords:
                if kw.lower() in recent_text.lower():
                    # 检查是否已询问过
                    if category in self._asked_decisions:
                        continue

                    # 检查是否有分歧（双方都在讨论这个话题）
                    if self._debate_state.disagreement_points:
                        # 标记已询问
                        self._asked_decisions.add(category)
                        return {
                            "category": category,
                            "keyword": kw,
                            "question": f"关于【{category}】，您的倾向或约束是什么？",
                            "options": self._get_decision_options(category),
                        }

        return None

    def _get_decision_options(self, category: str) -> list[str]:
        """获取关键决策的默认选项"""
        OPTIONS = {
            "技术栈": ["React", "Vue", "其他框架", "无特定要求"],
            "预算": ["低成本优先", "平衡成本与质量", "质量优先"],
            "时间": ["1-3个月", "3-6个月", "6个月以上"],
            "团队": ["1-3人", "3-5人", "5人以上"],
            "架构": ["单体架构", "微服务", "混合架构"],
        }
        return OPTIONS.get(category, [])

    def _generate_stalemate_question(self) -> dict:
        """生成僵局询问

        Returns:
            僵局询问事件数据
        """
        # 获取最近分歧点
        disagreements = self._debate_state.disagreement_points[-3:]
        disagreement_summary = (
            "\n".join(f"• {d[:100]}" for d in disagreements)
            if disagreements
            else "双方观点差异"
        )

        return {
            "type": "stalemate_question",
            "topic": self._topic,
            "disagreements": disagreement_summary,
            "rounds": self._debate_state.round_num,
            "question": f"辩论已进行 {self._debate_state.round_num} 轮，双方僵持不下。\n请您给出看法或倾向，帮助打破僵局：",
        }

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
        unique_disagreement = list(
            dict.fromkeys(self._debate_state.disagreement_points[-10:])
        )

        # PRD条目分类
        prd_items = getattr(self._debate_state, "prd_items", [])
        categorized_items = self._categorize_prd_items(prd_items)

        # 精简概述（只取PRD基础版的前300字）
        overview = self._prd_base if self._prd_base else "待完善"

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
        product_keywords = [
            "用户",
            "目标",
            "功能",
            "体验",
            "需求",
            "价值",
            "MVP",
            "验证",
        ]
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
