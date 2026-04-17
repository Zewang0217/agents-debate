"""Agent 模块：辩论 Agent 和中控 Agent"""

from .debater import DebaterAgent, create_debater_pair
from .moderator import ModeratorAgent, ModeratorState, DebateRecord

__all__ = [
    "DebaterAgent",
    "create_debater_pair",
    "ModeratorAgent",
    "ModeratorState",
    "DebateRecord",
]