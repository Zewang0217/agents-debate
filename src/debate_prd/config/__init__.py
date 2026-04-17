"""配置模块：预设角色、提示词、参数设置"""

from .presets import DEBATER_PRESETS, get_preset, list_presets
from .settings import Settings, LLMConfig, DEFAULT_SETTINGS, DEFAULT_LLM_CONFIG

__all__ = [
    "DEBATER_PRESETS",
    "get_preset",
    "list_presets",
    "Settings",
    "LLMConfig",
    "DEFAULT_SETTINGS",
    "DEFAULT_LLM_CONFIG",
]