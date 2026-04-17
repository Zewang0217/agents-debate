"""配置参数：轮数上限、终止条件、LLM 配置等"""

from dataclasses import dataclass, field
import os


@dataclass
class LLMConfig:
    """LLM 模型配置（兼容 OpenAI 格式）"""

    api_key: str = ""
    """API Key，支持从环境变量读取"""

    base_url: str = "https://api.openai.com/v1"
    """API Base URL，可自定义以使用其他兼容 OpenAI 的服务"""

    model: str = "gpt-4o-mini"
    """模型名称"""

    temperature: float = 0.7
    """生成温度"""

    max_tokens: int = 2048
    """最大输出 token 数"""

    model_info: dict = field(default_factory=lambda: {
        "vision": False,
        "function_calling": True,
        "json_output": True,
        "family": "unknown",
        "structured_output": True,
    })
    """模型能力信息（非OpenAI模型必需）"""

    def __post_init__(self):
        """初始化后处理：从环境变量读取默认值"""
        if not self.api_key:
            self.api_key = os.environ.get("OPENAI_API_KEY", "")

        # 支持环境变量覆盖 base_url
        env_base_url = os.environ.get("OPENAI_BASE_URL", "")
        if env_base_url:
            self.base_url = env_base_url

        # 支持环境变量覆盖 model
        env_model = os.environ.get("OPENAI_MODEL", "")
        if env_model:
            self.model = env_model

        # 根据模型名称自动设置model_info
        self._auto_detect_model_info()

    def _auto_detect_model_info(self) -> None:
        """根据模型名称自动检测model_info"""
        model_lower = self.model.lower()

        # DeepSeek模型
        if "deepseek" in model_lower:
            self.model_info = {
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "family": "deepseek",
                "structured_output": True,
            }
        # Ollama本地模型
        elif self.base_url and ("localhost" in self.base_url or "11434" in self.base_url):
            self.model_info = {
                "vision": False,
                "function_calling": True,
                "json_output": False,
                "family": "unknown",
                "structured_output": False,
            }
        # 其他自定义模型
        elif self.base_url != "https://api.openai.com/v1":
            self.model_info = {
                "vision": False,
                "function_calling": True,
                "json_output": True,
                "family": "unknown",
                "structured_output": True,
            }

    @classmethod
    def from_env(cls) -> "LLMConfig":
        """从环境变量创建配置

        环境变量:
        - OPENAI_API_KEY: API Key
        - OPENAI_BASE_URL: API Base URL
        - OPENAI_MODEL: 模型名称
        """
        return cls(
            api_key=os.environ.get("OPENAI_API_KEY", ""),
            base_url=os.environ.get("OPENAI_BASE_URL", "https://api.openai.com/v1"),
            model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        )

    def to_client_kwargs(self) -> dict:
        """转换为 OpenAIChatCompletionClient 参数"""
        kwargs = {
            "model": self.model,
            "api_key": self.api_key,
        }
        # 非OpenAI模型需要base_url和model_info
        if self.base_url != "https://api.openai.com/v1":
            kwargs["base_url"] = self.base_url
            kwargs["model_info"] = self.model_info
        return kwargs


@dataclass
class Settings:
    """系统配置参数"""

    # LLM 配置
    llm: LLMConfig = field(default_factory=LLMConfig)
    """LLM 模型配置"""

    # 辩论控制
    max_rounds: int = 10
    """辩论轮数上限，超过触发用户介入"""

    max_total_rounds: int = 20
    """总轮数上限（含澄清和介入），超过强制终止"""

    # 触发条件
    intervention_keyword: str = "仲裁"
    """用户触发介入的关键词"""

    stalemate_rounds: int = 3
    """僵局检测：连续 N 轮无新观点则判定僵局"""

    # 输出
    prd_output_dir: str = "./output"
    """PRD 文件输出目录"""

    debate_record_file: str = "debate_history.md"
    """辩论记录文件名"""

    # Agent 配置
    clarification_rounds: int = 3
    """澄清阶段的最多轮数"""

    consensus_threshold: float = 0.7
    """共识阈值：70% 以上议题达成共识视为完成"""


# 默认配置实例
DEFAULT_SETTINGS = Settings()
DEFAULT_LLM_CONFIG = LLMConfig()