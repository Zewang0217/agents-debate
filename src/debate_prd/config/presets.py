"""预设角色配置：三种辩论角色组合"""

from typing import TypedDict


class DebaterConfig(TypedDict):
    """辩论 Agent 配置"""
    role: str
    stance: str
    focus_areas: list[str]


class PresetConfig(TypedDict):
    """预设配置"""
    debater1: DebaterConfig
    debater2: DebaterConfig
    description: str


DEBATER_PRESETS: dict[str, PresetConfig] = {
    "pm_vs_dev": {
        "description": "产品需求视角 vs 技术可行性视角",
        "debater1": {
            "role": "PM",
            "stance": "产品价值优先，用户需求驱动，快速验证市场",
            "focus_areas": [
                "用户价值和体验",
                "市场需求和竞品分析",
                "功能完整性和优先级",
                "快速迭代验证",
            ],
        },
        "debater2": {
            "role": "Dev",
            "stance": "技术可行性优先，实现成本考量，系统稳定性",
            "focus_areas": [
                "技术实现难度",
                "系统架构和性能",
                "开发成本和时间",
                "技术债务和风险",
            ],
        },
    },
    "business_vs_security": {
        "description": "业务增长视角 vs 安全合规视角",
        "debater1": {
            "role": "Business",
            "stance": "业务增长优先，快速迭代，抢占市场先机",
            "focus_areas": [
                "业务价值和ROI",
                "市场机会和时效性",
                "用户增长和转化",
                "快速上线验证",
            ],
        },
        "debater2": {
            "role": "Security",
            "stance": "安全合规优先，风险控制，数据保护",
            "focus_areas": [
                "数据安全和隐私",
                "合规要求和法规",
                "安全漏洞风险",
                "权限和审计",
            ],
        },
    },
    "ux_vs_architecture": {
        "description": "用户体验视角 vs 系统架构视角",
        "debater1": {
            "role": "UX",
            "stance": "用户体验优先，交互流畅，界面友好",
            "focus_areas": [
                "用户操作流程",
                "界面设计和布局",
                "交互反馈和响应",
                "易用性和学习成本",
            ],
        },
        "debater2": {
            "role": "Arch",
            "stance": "系统架构优先，性能稳定，扩展性好",
            "focus_areas": [
                "系统性能和响应",
                "架构设计和扩展性",
                "资源消耗和成本",
                "维护和升级难度",
            ],
        },
    },
}


def get_preset(name: str) -> PresetConfig:
    """获取预设配置

    Args:
        name: 预设名称，可选值: pm_vs_dev, business_vs_security, ux_vs_architecture

    Returns:
        PresetConfig: 预设配置字典

    Raises:
        ValueError: 预设名称不存在
    """
    if name not in DEBATER_PRESETS:
        available = ", ".join(DEBATER_PRESETS.keys())
        raise ValueError(f"预设 '{name}' 不存在，可选: {available}")
    return DEBATER_PRESETS[name]


def list_presets() -> list[str]:
    """列出所有预设名称"""
    return list(DEBATER_PRESETS.keys())