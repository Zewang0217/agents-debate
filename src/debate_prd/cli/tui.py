"""
辩论式 PRD 生成系统 - 炫酷 TUI 界面

使用 Textual 框架构建交互式终端界面
深色简约 + 赛博朋克风格
"""

from textual.app import App, ComposeResult
from textual.widgets import (
    Header,
    Footer,
    Static,
    Button,
    Input,
    Select,
    TextArea,
    Label,
)
from textual.containers import Container, Vertical, VerticalScroll
from textual.binding import Binding
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text
from rich.style import Style
import asyncio
import os

from ..config.presets import get_preset, list_presets, DEBATER_PRESETS
from ..config.settings import LLMConfig, Settings
from ..team.debate_team import DebateTeam


# ========== 主题配色 ==========
# 深蓝灰背景 + 霓虹蓝紫主色 + 赛博绿红强调

THEME = {
    "bg_dark": "#0d1117",       # 最深背景
    "bg_panel": "#161b22",      # 面板背景
    "bg_card": "#21262d",       # 卡片背景
    "border": "#30363d",        # 边框
    "text_dim": "#8b949e",      # 暗淡文字
    "text": "#c9d1d9",          # 正常文字
    "accent_blue": "#58a6ff",   # 霓虹蓝
    "accent_purple": "#bc8cff", # 霓虹紫
    "success": "#3fb950",       # 赛博绿
    "error": "#f85149",         # 赛博红
    "warning": "#d29922",       # 赛博橙
}


# ========== 自定义消息类型 ==========

class DebateStarted(Message):
    """辩论开始消息"""
    def __init__(self, preset: str, topic: str) -> None:
        super().__init__()
        self.preset = preset
        self.topic = topic


class NewDebateMessage(Message):
    """新辩论消息"""
    def __init__(self, speaker: str, role: str, content: str) -> None:
        super().__init__()
        self.speaker = speaker
        self.role = role
        self.content = content


class DebateComplete(Message):
    """辩论完成消息"""
    def __init__(self, prd: str) -> None:
        super().__init__()
        self.prd = prd


# ========== 自定义组件 ==========

class DebateMessage(Static):
    """单条辩论消息组件 - 简洁赛博风格"""

    def __init__(self, speaker: str, role: str, content: str, is_user: bool = False) -> None:
        super().__init__()
        self.speaker = speaker
        self.role = role
        self.content = content
        self.is_user = is_user

    def render(self) -> Text:
        # 赛博朋克配色
        colors = {
            "moderator": (THEME["accent_purple"], "◇"),
            "debater1": (THEME["accent_blue"], "◆"),
            "debater2": (THEME["warning"], "◆"),
            "user": (THEME["success"], "●"),
        }
        color, symbol = colors.get(self.speaker.lower(), (THEME["text"], "○"))

        # 简洁格式：符号 + 角色 + 内容
        text = Text()
        text.append(f"{symbol} ", style=Style(color=color, bold=True))
        text.append(f"{self.role}: ", style=Style(color=THEME["text_dim"]))
        text.append(self.content[:150])
        if len(self.content) > 150:
            text.append("…", style=Style(color=THEME["text_dim"]))
        return text


class ControlPanel(Vertical):
    """控制面板 - 精简左侧栏"""

    DEFAULT_CSS = f"""
    ControlPanel {{
        width: 20%;
        height: 100%;
        dock: left;
        background: {THEME["bg_panel"]};
        padding: 1 2;
        border-right: solid {THEME["border"]};
    }}

    ControlPanel Label {{
        color: {THEME["accent_blue"]};
        text-style: bold;
        margin: 1 0;
    }}

    ControlPanel Select {{
        background: {THEME["bg_card"]};
        border: solid {THEME["border"]};
        margin: 0 0 2 0;
    }}

    ControlPanel Input {{
        background: {THEME["bg_card"]};
        border: solid {THEME["border"]};
        color: {THEME["text"]};
        margin: 0 0 2 0;
    }}

    ControlPanel TextArea {{
        background: {THEME["bg_card"]};
        border: solid {THEME["border"]};
        color: {THEME["text"]};
        height: 6;
        margin: 0 0 2 0;
    }}

    ControlPanel Button {{
        margin: 1 0;
        background: {THEME["bg_card"]};
    }}

    ControlPanel #llm-info {{
        color: {THEME["text_dim"]};
        padding: 1;
    }}

    ControlPanel #start-btn {{
        background: {THEME["accent_blue"]};
        color: {THEME["bg_dark"]};
    }}

    ControlPanel #arbitrate-btn {{
        background: {THEME["warning"]};
        color: {THEME["bg_dark"]};
    }}

    ControlPanel #stop-btn {{
        background: {THEME["error"]};
        color: {THEME["bg_dark"]};
    }}
    """

    def compose(self) -> ComposeResult:
        # 精简标签
        yield Label("角色")
        yield Select(
            [(k, k) for k in list_presets()],  # 简化显示
            prompt="选择...",
            id="preset-select",
        )

        yield Label("议题")
        # 用Input替代TextArea以支持中文输入
        yield Input(
            placeholder="输入产品需求...",
            id="topic-input",
        )

        # LLM信息 - 简化显示
        llm_info = self._get_llm_info()
        yield Static(llm_info, id="llm-info")

        # 精简按钮文字
        yield Button("开始", id="start-btn", variant="primary")
        yield Button("仲裁", id="arbitrate-btn", variant="warning", disabled=True)
        yield Button("停止", id="stop-btn", variant="error", disabled=True)

    def _get_llm_info(self) -> str:
        """获取 LLM 配置信息 - 简化"""
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return f"▸ {model}"


class DebateView(VerticalScroll):
    """辩论显示区域 - 宽幅赛博风格"""

    DEFAULT_CSS = f"""
    DebateView {{
        width: 65%;
        height: 100%;
        background: {THEME["bg_dark"]};
        padding: 1 2;
    }}

    DebateView .welcome {{
        color: {THEME["accent_purple"]};
        text-style: bold;
        text-align: center;
        padding: 2;
    }}

    DebateView DebateMessage {{
        margin: 0 0 1 0;
        padding: 1;
        background: {THEME["bg_card"]};
        border-left: solid {THEME["accent_blue"]};
    }}
    """

    messages: reactive[list] = reactive([])

    def compose(self) -> ComposeResult:
        # 极简欢迎文字
        yield Static(
            "◆ 辩论式 PRD 生成\n\n选择角色 → 输入议题 → 开始",
            id="welcome-text",
            classes="welcome",
        )

    def add_message(self, speaker: str, role: str, content: str, is_user: bool = False) -> None:
        """添加新消息"""
        self.messages.append((speaker, role, content, is_user))
        msg_widget = DebateMessage(speaker, role, content, is_user)

        # 移除欢迎文字
        try:
            welcome = self.query_one("#welcome-text")
            welcome.remove()
        except:
            pass

        self.mount(msg_widget)
        self.scroll_end(animate=False)


class StatusPanel(Vertical):
    """状态面板 - 紧凑右侧栏"""

    DEFAULT_CSS = f"""
    StatusPanel {{
        width: 15%;
        height: 100%;
        dock: right;
        background: {THEME["bg_panel"]};
        padding: 1 2;
        border-left: solid {THEME["border"]};
    }}

    StatusPanel Label {{
        color: {THEME["accent_blue"]};
        text-style: bold;
        margin: 1 0;
    }}

    StatusPanel Static {{
        color: {THEME["text_dim"]};
        margin: 0 0 1 0;
    }}

    StatusPanel #status-text {{
        color: {THEME["accent_purple"]};
        text-style: bold;
    }}

    StatusPanel #role-info {{
        color: {THEME["text"]};
        padding: 1;
        background: {THEME["bg_card"]};
    }}

    StatusPanel #prd-preview {{
        height: 8;
        background: {THEME["bg_card"]};
        border: solid {THEME["border"]};
        color: {THEME["text_dim"]};
    }}
    """

    round_count: reactive[int] = reactive(0)
    status: reactive[str] = reactive("待开始")

    def compose(self) -> ComposeResult:
        yield Label("状态")
        yield Static(self.status, id="status-text")

        yield Label("角色")
        yield Static("", id="role-info")

        yield Label("轮数")
        yield Static("0", id="round-stat")

        yield Label("PRD")
        yield TextArea(id="prd-preview", disabled=True)

    def update_stats(self, round_num: int, consensus: int, disagreement: int) -> None:
        """更新统计"""
        self.round_count = round_num
        self.query_one("#round-stat", Static).update(f"{round_num}")

    def update_status(self, status: str) -> None:
        """更新状态"""
        self.status = status
        self.query_one("#status-text", Static).update(status)

    def update_roles(self, preset: str) -> None:
        """更新角色"""
        config = get_preset(preset)
        role_info = f"◆ {config['debater1']['role']}\n◆ {config['debater2']['role']}"
        self.query_one("#role-info", Static).update(role_info)

    def update_prd_preview(self, prd: str) -> None:
        """更新PRD预览"""
        preview = self.query_one("#prd-preview", TextArea)
        preview.text = prd[:300] + "…" if len(prd) > 300 else prd


# ========== 主应用 ==========

class DebateTUIApp(App):
    """辩论式 PRD 生成系统 - 赛博朋克 TUI"""

    CSS = f"""
    Screen {{
        layout: horizontal;
        background: {THEME["bg_dark"]};
    }}

    Header {{
        background: {THEME["bg_panel"]};
        color: {THEME["accent_blue"]};
        border-bottom: solid {THEME["border"]};
    }}

    Footer {{
        background: {THEME["bg_panel"]};
        border-top: solid {THEME["border"]};
    }}
    """

    BINDINGS = [
        Binding("s", "start_debate", "开始"),
        Binding("a", "request_arbitration", "仲裁"),
        Binding("q", "quit", "退出"),
        Binding("d", "toggle_dark", "主题"),
    ]

    TITLE = "◆ 辩论式 PRD 生成"
    SUB_TITLE = "Agent Debate → PRD"

    debate_running: reactive[bool] = reactive(False)
    debate_team: DebateTeam | None = None
    debate_task: asyncio.Task | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield ControlPanel()
        yield DebateView()
        yield StatusPanel()
        yield Footer()

    def on_select_changed(self, event: Select.Changed) -> None:
        """预设选择"""
        if event.select.id == "preset-select":
            preset = event.value
            self.query_one(StatusPanel).update_roles(preset)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """按钮点击"""
        if event.button.id == "start-btn":
            self.action_start_debate()
        elif event.button.id == "arbitrate-btn":
            self.action_request_arbitration()
        elif event.button.id == "stop-btn":
            self.action_stop_debate()

    def action_start_debate(self) -> None:
        """开始辩论"""
        if self.debate_running:
            return

        preset_select = self.query_one("#preset-select", Select)
        topic_input = self.query_one("#topic-input", Input)

        preset = preset_select.value or "pm_vs_dev"
        topic = topic_input.value.strip() or "通用产品需求"

        self.debate_running = True
        self.query_one(StatusPanel).update_status("● 辩论中")
        self.query_one("#start-btn", Button).disabled = True
        self.query_one("#arbitrate-btn", Button).disabled = False
        self.query_one("#stop-btn", Button).disabled = False

        self.debate_task = asyncio.create_task(self._run_debate(preset, topic))

    def action_request_arbitration(self) -> None:
        """请求仲裁"""
        debate_view = self.query_one(DebateView)
        debate_view.add_message("user", "用户", "● [仲裁] 请介入决策")
        self.query_one(StatusPanel).update_status("● 等待仲裁")

    def action_stop_debate(self) -> None:
        """停止辩论"""
        if self.debate_task:
            self.debate_task.cancel()
        self._end_debate()

    def action_toggle_dark(self) -> None:
        """切换主题"""
        self.theme = "textual-dark" if self.theme != "textual-dark" else "nord"

    async def _run_debate(self, preset: str, topic: str) -> None:
        """运行辩论"""
        debate_view = self.query_one(DebateView)
        status_panel = self.query_one(StatusPanel)

        debate_view.add_message("moderator", "Moderator", f"● 开始辩论：{topic[:50]}")
        status_panel.update_roles(preset)

        try:
            llm_config = LLMConfig.from_env()
            if not llm_config.api_key:
                debate_view.add_message("moderator", "Moderator", "◆ 请配置API Key")
                self._end_debate()
                return

            from autogen_ext.models.openai import OpenAIChatCompletionClient

            model_client = OpenAIChatCompletionClient(**llm_config.to_client_kwargs())

            settings = Settings(llm=llm_config, max_rounds=6)
            team = DebateTeam(preset=preset, model_client=model_client, settings=settings)
            self.debate_team = team

            preset_config = get_preset(preset)
            round_num = 0

            stream = team.run_stream(topic)

            async for event in stream:
                if hasattr(event, "messages"):
                    for msg in event.messages:
                        speaker = getattr(msg, "source", "system")
                        content = str(getattr(msg, "content", msg))

                        role = preset_config["debater1"]["role"] if "debater1" in speaker.lower() \
                            else preset_config["debater2"]["role"] if "debater2" in speaker.lower() \
                            else "Moderator"

                        debate_view.add_message(speaker, role, content)

                        if "debater" in speaker.lower():
                            round_num += 1
                        status_panel.update_stats(round_num, round_num // 2, round_num // 3)

                        if "[PRD_COMPLETE]" in content:
                            prd = content.replace("[PRD_COMPLETE]", "").strip()
                            status_panel.update_prd_preview(prd)
                            debate_view.add_message("moderator", "Moderator", "◆ PRD已生成")
                            self._end_debate()
                            return

        except asyncio.CancelledError:
            debate_view.add_message("moderator", "Moderator", "◆ 已停止")
            self._end_debate()

        except Exception as e:
            debate_view.add_message("moderator", "Moderator", f"◆ 错误: {str(e)[:80]}")
            self._end_debate()

    def _end_debate(self) -> None:
        """结束辩论"""
        self.debate_running = False
        self.debate_task = None

        self.query_one(StatusPanel).update_status("◆ 完成")
        self.query_one("#start-btn", Button).disabled = False
        self.query_one("#arbitrate-btn", Button).disabled = True
        self.query_one("#stop-btn", Button).disabled = True


def run_tui():
    """启动 TUI"""
    app = DebateTUIApp()
    app.run()


if __name__ == "__main__":
    run_tui()