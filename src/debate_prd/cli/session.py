"""交互会话状态管理"""

import os
from dataclasses import dataclass, field

from ..config.settings import LLMConfig
from ..config.presets import list_presets


@dataclass
class InteractiveSession:
    """交互会话状态"""

    llm_config: LLMConfig = field(default_factory=LLMConfig)
    preset: str = "pm_vs_dev"
    topic: str | None = None
    max_rounds: int = 6
    output_dir: str = "./output"
    running: bool = True

    def load_from_env(self) -> None:
        """从环境变量加载默认配置"""
        self.llm_config = LLMConfig.from_env()

    def is_ready_for_debate(self) -> bool:
        """检查是否可以启动辩论"""
        return bool(self.llm_config.api_key) and bool(self.topic)

    def validate_config(self) -> list[str]:
        """验证配置完整性，返回缺失项列表"""
        missing = []
        if not self.llm_config.api_key:
            missing.append("API Key 未设置")
        if not self.topic:
            missing.append("议题未设置")
        return missing

    def mask_api_key(self) -> str:
        """隐藏 API Key 显示"""
        key = self.llm_config.api_key
        if not key:
            return "(未设置)"
        if len(key) <= 8:
            return "sk-***"
        return f"{key[:4]}...{key[-4:]}"

    def to_display_dict(self) -> dict:
        """转换为可显示字典"""
        return {
            "api_key": self.mask_api_key(),
            "api_key_set": bool(self.llm_config.api_key),
            "base_url": self.llm_config.base_url,
            "model": self.llm_config.model,
            "preset": self.preset,
            "max_rounds": self.max_rounds,
            "output_dir": self.output_dir,
            "topic": self.topic or "(未设置)",
        }

    def set_config(self, key: str, value: str) -> bool:
        """设置配置参数

        Returns:
            True if successful, False if unknown key
        """
        valid_keys = [
            "api_key",
            "base_url",
            "model",
            "preset",
            "max_rounds",
            "output_dir",
        ]

        if key not in valid_keys:
            return False

        if key == "api_key":
            self.llm_config.api_key = value
        elif key == "base_url":
            self.llm_config.base_url = value
        elif key == "model":
            self.llm_config.model = value
        elif key == "preset":
            if value in list_presets():
                self.preset = value
            else:
                return False
        elif key == "max_rounds":
            try:
                self.max_rounds = int(value)
            except ValueError:
                return False
        elif key == "output_dir":
            self.output_dir = value

        return True
