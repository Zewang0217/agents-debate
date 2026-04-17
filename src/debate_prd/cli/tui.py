"""
辩论式 PRD 生成系统 - 炫酷 TUI 界面

使用 Textual 框架构建交互式终端界面
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
from textual.containers import Container, Vertical, Horizontal, VerticalScroll
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
    """单条辩论消息组件"""

    def __init__(self, speaker: str, role: str, content: str, is_user: bool = False) -> None:
        super().__init__()
        self.speaker = speaker
        self.role = role
        self.content = content
        self.is_user = is_user

    def render(self) -> Text:
        # 根据发言者选择颜色
        colors = {
            "moderator": ("cyan", "🎯 Moderator"),
            "debater1": ("green", f"🎭 {self.role}"),
            "debater2": ("yellow", f"🎭 {self.role}"),
            "user": ("magenta", "👤 用户"),
        }
        color, label = colors.get(self.speaker.lower(), ("white", self.speaker))

        # 构建消息
        text = Text()
        text.append(f"{label}: ", style=Style(color=color, bold=True))
        text.append(self.content[:200])
        if len(self.content) > 200:
            text.append("...", style=Style(color="dim"))
        return text


class ControlPanel(Vertical):
    """控制面板：预设选择、议题输入、控制按钮"""

    DEFAULT_CSS = """
    ControlPanel {
        width: 25%;
        height: 100%;
        dock: left;
        background: $surface;
        padding: 1;
        border-right: solid $primary;
    }

    ControlPanel Label {
        margin: 1 0 0 0;
        color: $accent;
        text-style: bold;
    }

    ControlPanel Select, ControlPanel Input {
        margin: 0 0 1 0;
    }

    ControlPanel Button {
        margin: 1 0;
    }

    ControlPanel .divider {
        height: 1;
        background: $primary;
        margin: 1 0;
    }

    ControlPanel TextArea {
        height: 8;
        margin: 0 0 1 0;
    }

    ControlPanel #llm-info {
        color: $text-muted;
        text-style: italic;
    }
    """

    def compose(self) -> ComposeResult:
        yield Label("🎯 角色预设")
        yield Select(
            [(f"{k} - {DEBATER_PRESETS[k]['description']}", k) for k in list_presets()],
            prompt="选择预设组合...",
            id="preset-select",
        )

        yield Static("", classes="divider")

        yield Label("📝 辩论议题")
        yield TextArea(id="topic-input", placeholder="描述你想要开发的产品或功能需求...")

        yield Static("", classes="divider")

        # LLM 配置显示
        llm_info = self._get_llm_info()
        yield Static(llm_info, id="llm-info")

        yield Static("", classes="divider")

        yield Button("▶ 开始辩论", id="start-btn", variant="primary")
        yield Button("⏸ 请求仲裁", id="arbitrate-btn", variant="warning", disabled=True)
        yield Button("⏹ 停止", id="stop-btn", variant="error", disabled=True)

    def _get_llm_info(self) -> str:
        """获取 LLM 配置信息"""
        base_url = os.environ.get("OPENAI_BASE_URL", "api.openai.com")
        model = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")
        return f"🔗 {base_url}\n📦 {model}"


class DebateView(VerticalScroll):
    """辩论显示区域：实时显示辩论消息"""

    DEFAULT_CSS = """
    DebateView {
        width: 55%;
        height: 100%;
        background: $background;
        padding: 1;
        border-left: solid $primary;
        border-right: solid $primary;
    }

    DebateView .welcome {
        color: $accent;
        text-style: bold;
        text-align: center;
        margin: 2;
    }

    DebateView DebateMessage {
        margin: 0 0 1 0;
        padding: 1;
        background: $surface-darken-1;
    }
    """

    messages: reactive[list] = reactive([])

    def compose(self) -> ComposeResult:
        yield Static(
            "🎮 辩论式 PRD 生成系统\n\n"
            "左侧选择角色预设，输入议题后点击「开始辩论」\n\n"
            "辩论过程中可随时请求仲裁介入",
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
        # 自动滚动到底部
        self.scroll_end(animate=False)


class StatusPanel(Vertical):
    """状态面板：显示辩论状态和统计"""

    DEFAULT_CSS = """
    StatusPanel {
        width: 20%;
        height: 100%;
        dock: right;
        background: $surface;
        padding: 1;
        border-left: solid $primary;
    }

    StatusPanel Label {
        margin: 1 0 0 0;
        color: $accent;
        text-style: bold;
    }

    StatusPanel Static {
        margin: 0 0 1 0;
    }

    StatusPanel .stat-box {
        background: $surface-darken-1;
        padding: 1;
        margin: 1 0;
    }

    StatusPanel .stat-value {
        color: $success;
        text-style: bold;
    }

    StatusPanel .divider {
        height: 1;
        background: $primary;
        margin: 1 0;
    }

    StatusPanel #role-info {
        color: $text;
    }

    StatusPanel #prd-preview {
        height: 10;
        background: $surface-darken-2;
        padding: 1;
    }
    """

    round_count: reactive[int] = reactive(0)
    consensus_count: reactive[int] = reactive(0)
    disagreement_count: reactive[int] = reactive(0)
    status: reactive[str] = reactive("待开始")

    def compose(self) -> ComposeResult:
        yield Label("📊 辩论状态")
        yield Static(self.status, id="status-text")

        yield Static("", classes="divider")

        yield Label("📈 统计")
        with Container(classes="stat-box"):
            yield Static(f"轮数: 0/{10}", id="round-stat")
            yield Static(f"共识: 0", id="consensus-stat", classes="stat-value")
            yield Static(f"分歧: 0", id="disagreement-stat")

        yield Static("", classes="divider")

        yield Label("🎭 角色信息")
        yield Static("", id="role-info")

        yield Static("", classes="divider")

        yield Label("📄 PRD 预览")
        yield TextArea(id="prd-preview", disabled=True)


    def update_stats(self, round_num: int, consensus: int, disagreement: int) -> None:
        """更新统计数据"""
        self.round_count = round_num
        self.consensus_count = consensus
        self.disagreement_count = disagreement

        self.query_one("#round-stat", Static).update(f"轮数: {round_num}/10")
        self.query_one("#consensus-stat", Static).update(f"共识: {consensus}")
        self.query_one("#disagreement-stat", Static).update(f"分歧: {disagreement}")

    def update_status(self, status: str) -> None:
        """更新状态"""
        self.status = status
        self.query_one("#status-text", Static).update(status)

    def update_roles(self, preset: str) -> None:
        """更新角色信息"""
        config = get_preset(preset)
        role_info = (
            f"🟢 {config['debater1']['role']}\n"
            f"   {config['debater1']['stance'][:30]}...\n\n"
            f"🟡 {config['debater2']['role']}\n"
            f"   {config['debater2']['stance'][:30]}..."
        )
        self.query_one("#role-info", Static).update(role_info)

    def update_prd_preview(self, prd: str) -> None:
        """更新 PRD 预览"""
        preview = self.query_one("#prd-preview", TextArea)
        preview.text = prd[:500] + "..." if len(prd) > 500 else prd


# ========== 主应用 ==========

class DebateTUIApp(App):
    """辩论式 PRD 生成系统 - TUI 主应用"""

    CSS = """
    Screen {
        layout: horizontal;
    }

    Header {
        background: $primary;
        color: $text-primary;
    }

    Footer {
        background: $surface;
    }
    """

    BINDINGS = [
        Binding("s", "start_debate", "开始"),
        Binding("a", "request_arbitration", "仲裁"),
        Binding("q", "quit", "退出"),
        Binding("d", "toggle_dark", "深色"),
        Binding("c", "clear_chat", "清空"),
    ]

    TITLE = "🎮 辩论式 PRD 生成系统"
    SUB_TITLE = "两个 Agent 辩论，生成更全面的 PRD"

    # 状态
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
        """预设选择变化"""
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

        # 获取预设和议题
        preset_select = self.query_one("#preset-select", Select)
        topic_input = self.query_one("#topic-input", TextArea)

        preset = preset_select.value or "pm_vs_dev"
        topic = topic_input.text.strip() or "一个通用的产品需求"

        # 更新状态
        self.debate_running = True
        self.query_one(StatusPanel).update_status("🔄 辩论中...")
        self.query_one("#start-btn", Button).disabled = True
        self.query_one("#arbitrate-btn", Button).disabled = False
        self.query_one("#stop-btn", Button).disabled = False

        # 启动辩论任务
        self.debate_task = asyncio.create_task(self._run_debate(preset, topic))

    def action_request_arbitration(self) -> None:
        """请求仲裁"""
        debate_view = self.query_one(DebateView)
        debate_view.add_message("user", "用户", "[仲裁] 请用户介入决策...", is_user=True)
        self.query_one(StatusPanel).update_status("⏳ 等待用户仲裁...")

    def action_stop_debate(self) -> None:
        """停止辩论"""
        if self.debate_task:
            self.debate_task.cancel()
        self._end_debate()

    def action_toggle_dark(self) -> None:
        """切换深色模式"""
        self.theme = "textual-dark" if self.theme == "textual-light" else "textual-light"

    def action_clear_chat(self) -> None:
        """清空辩论区"""
        debate_view = self.query_one(DebateView)
        for msg in debate_view.query(DebateMessage):
            msg.remove()
        debate_view.mount(Static(
            "🎮 辩论式 PRD 生成系统\n\n"
            "左侧选择角色预设，输入议题后点击「开始辩论」",
            id="welcome-text",
            classes="welcome",
        ))

    async def _run_debate(self, preset: str, topic: str) -> None:
        """运行辩论流程"""
        debate_view = self.query_one(DebateView)
        status_panel = self.query_one(StatusPanel)

        # 添加开始消息
        debate_view.add_message("moderator", "Moderator", f"开始辩论，议题：{topic}")
        status_panel.update_roles(preset)

        try:
            # 创建 LLM 客户端
            llm_config = LLMConfig.from_env()
            if not llm_config.api_key:
                debate_view.add_message("moderator", "Moderator", "❌ 请配置 API Key")
                self._end_debate()
                return

            # 导入 OpenAIChatCompletionClient
            from autogen_ext.models.openai import OpenAIChatCompletionClient

            model_client = OpenAIChatCompletionClient(**llm_config.to_client_kwargs())

            # 创建辩论团队
            settings = Settings(llm=llm_config, max_rounds=6)
            team = DebateTeam(preset=preset, model_client=model_client, settings=settings)
            self.debate_team = team

            preset_config = get_preset(preset)

            # 运行辩论流
            round_num = 0
            stream = team.run_stream(topic)

            async for event in stream:
                if hasattr(event, "messages"):
                    for msg in event.messages:
                        speaker = getattr(msg, "source", "system")
                        content = str(getattr(msg, "content", msg))

                        # 获取角色名称
                        if "debater1" in speaker.lower():
                            role = preset_config["debater1"]["role"]
                        elif "debater2" in speaker.lower():
                            role = preset_config["debater2"]["role"]
                        elif "moderator" in speaker.lower():
                            role = "Moderator"
                        else:
                            role = speaker

                        # 添加消息
                        debate_view.add_message(speaker, role, content)

                        # 更新统计
                        if "debater" in speaker.lower():
                            round_num += 1
                        status_panel.update_stats(round_num, round_num // 2, round_num // 3)

                        # 检查完成
                        if "[PRD_COMPLETE]" in content:
                            prd = content.replace("[PRD_COMPLETE]", "").strip()
                            status_panel.update_prd_preview(prd)
                            debate_view.add_message("moderator", "Moderator", "✅ PRD 已生成！")
                            self._end_debate()
                            return

        except asyncio.CancelledError:
            debate_view.add_message("moderator", "Moderator", "⏹ 辨论已停止")
            self._end_debate()

        except Exception as e:
            debate_view.add_message("moderator", "Moderator", f"❌ 辩论出错: {str(e)[:100]}")
            self._end_debate()

    def _end_debate(self) -> None:
        """结束辩论"""
        self.debate_running = False
        self.debate_task = None

        self.query_one(StatusPanel).update_status("✅ 已完成")
        self.query_one("#start-btn", Button).disabled = False
        self.query_one("#arbitrate-btn", Button).disabled = True
        self.query_one("#stop-btn", Button).disabled = True


# ========== 入口函数 ==========

def run_tui():
    """启动 TUI 应用"""
    app = DebateTUIApp()
    app.run()


if __name__ == "__main__":
    run_tui()