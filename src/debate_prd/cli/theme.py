"""Rosé Pine 主题颜色定义

参考 DESIGH.md 设计规范和 opencode TUI 实现。
颜色值必须为硬编码十六进制，Textual CSS 不支持变量语法。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class RosePineColors:
    """Rosé Pine (Dark) 主题颜色常量"""

    # === 背景色 ===
    BASE: str = "#191724"
    """全局背景色"""
    SURFACE: str = "#1f1d2e"
    """面板、卡片背景色"""
    OVERLAY: str = "#26233a"
    """悬浮、弹窗背景色"""

    # === 文本色 ===
    TEXT: str = "#e0def4"
    """主文本色"""
    SUBTLE: str = "#908caa"
    """次要文本、禁用状态"""
    MUTED: str = "#6e6a86"
    """边框、分割线、注释"""

    # === 状态色 ===
    LOVE: str = "#eb6f92"
    """错误/危险"""
    GOLD: str = "#f6c177"
    """警告/高亮/等待"""
    PINE: str = "#31748f"
    """成功/新增"""
    FOAM: str = "#9ccfd8"
    """信息/提示"""

    # === 强调色 ===
    IRIS: str = "#c4a7e7"
    """主色调/交互/聚焦"""
    ROSE: str = "#ebbcba"
    """次要高亮"""

    # === 补充色 ===
    HIGHLIGHT_LOW: str = "#21202e"
    HIGHLIGHT_MED: str = "#403d52"
    HIGHLIGHT_HIGH: str = "#524f67"


# 全局颜色实例
COLORS = RosePineColors()


# === 语义化颜色映射 ===
# 用于 CLI 和 TUI 的语义化颜色常量

BACKGROUND = COLORS.BASE
PANEL_BACKGROUND = COLORS.SURFACE
MENU_BACKGROUND = COLORS.OVERLAY

TEXT_PRIMARY = COLORS.TEXT
TEXT_SECONDARY = COLORS.SUBTLE
TEXT_MUTED = COLORS.MUTED

ERROR = COLORS.LOVE
WARNING = COLORS.GOLD
SUCCESS = COLORS.PINE
INFO = COLORS.FOAM

PRIMARY = COLORS.IRIS
SECONDARY = COLORS.ROSE

BORDER = COLORS.MUTED
BORDER_ACTIVE = COLORS.IRIS