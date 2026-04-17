"""Team 模块：辩论团队编排"""

from .debate_team import DebateTeam, create_debate_team
from .termination import StalemateTermination, InterventionTermination

__all__ = [
    "DebateTeam",
    "create_debate_team",
    "StalemateTermination",
    "InterventionTermination",
]