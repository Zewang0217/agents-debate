"""辩论状态数据类

从 debate_loop.py 拆分，包含：
- ModeratorState - 中控状态机
- ConsensusPoint - 共识点
- DisagreementPoint - 分歧点
- DebateState - 辩论状态
- 其他辅助状态类

遵循规范：
- 纯数据类，无业务逻辑
- 使用 dataclass 简化定义
"""

from dataclasses import dataclass, field
from enum import Enum


class ModeratorState(Enum):
    """中控状态机"""

    CLARIFICATION = "clarification"
    PRD_QUESTIONING = "prd_questioning"
    DEBATE = "debate"
    INTERVENTION = "intervention"
    SYNTHESIS = "synthesis"
    COMPLETE = "complete"


@dataclass
class ConsensusPoint:
    """共识点"""

    content: str
    category: str = ""
    locked: bool = False
    evidence: list[str] = field(default_factory=list)
    round_created: int = 0


@dataclass
class DisagreementPoint:
    """分歧点"""

    topic: str
    pm_position: str = ""
    dev_position: str = ""
    priority: str = "normal"
    category: str = ""
    round_created: int = 0
    attempts: int = 0
    resolved: bool = False
    resolution: str = ""


@dataclass
class PRDItem:
    """PRD 条目"""

    content: str
    source: str = ""
    status: str = "pending"
    category: str = ""


@dataclass
class ClarificationState:
    """澄清状态"""

    messages: list = field(default_factory=list)
    collected_info: dict = field(default_factory=dict)
    rounds: int = 0


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

    locked_consensus: list[ConsensusPoint] = field(default_factory=list)
    pending_consensus: list[ConsensusPoint] = field(default_factory=list)
    active_disagreements: list[DisagreementPoint] = field(default_factory=list)

    prd_supplement: str = ""
    prd_items: list[PRDItem] = field(default_factory=list)

    debate_summary: list[dict] = field(default_factory=list)

    user_decisions: list[dict] = field(default_factory=list)

    agree_points: list[str] = field(default_factory=list)
    partial_agree_points: list[str] = field(default_factory=list)
    disagreement_points: list[str] = field(default_factory=list)
    consensus_points: list[str] = field(default_factory=list)
    stalemate_count: int = 0


__all__ = [
    "ModeratorState",
    "ConsensusPoint",
    "DisagreementPoint",
    "PRDItem",
    "ClarificationState",
    "PRDQuestioningState",
    "GuidanceState",
    "DebateState",
]
