"""
辩论式 PRD 生成系统 - 炫酷 TUI 界面

深色简约 + 赛博朋克风格
支持流式输出（逐字显示）
"""

from textual.app import App, ComposeResult
from textual.widgets import (
    Header,
    Footer,
    Static,
    Button,
    Label,
)
from textual.containers import Vertical, VerticalScroll
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

THEME = {
    "bg_dark": "#0d1117",
    "bg_panel": "#161b22",
    "bg_card": "#21262d",
    "border": "#30363d",
    "text_dim": "#8b949e",
    "text": "#c9d1d9",
    "accent_blue": "#58a6ff",
    "accent_purple": "#bc8cff",
    "success": "#3fb950",
    "error": "#f85149",
    "warning": "#d29922",
}


# ========== 消息类型 ==========

class DebateStarted(Message):
    def __init__(self, preset: str, topic: str) -> None:
        super().__init__()
        self.preset = preset
        self.topic = topic


class StreamingChunk(Message):
    """流式输出chunk"""
    def __init__(self, speaker: str, chunk: str) -> None:
        super().__init__()
        self.speaker = speaker
        self.chunk = chunk


class MessageComplete(Message):
    """消息完成"""
    def __init__(self, speaker: str, role: str, content: str) -> None:
        super().__init__()
        self.speaker = speaker
        self.role = role
        self.content = content


class DebateComplete(Message):
    def __init__(self, prd: str) -> None:
        super().__init__()
        self.prd = prd


# ========== 流式消息组件 ==========

class StreamingMessage(Static):
    """流式消息组件 - 支持逐字追加"""

    def __init__(self, speaker: str, role: str) -> None:
        super().__init__()
        self.speaker = speaker
        self.role = role
        self._content = ""
        self._chunks = []

        # 配色
        self.colors = {
            "moderator": THEME["accent_purple"],
            "debater1": THEME["accent_blue"],
            "debater2": THEME["warning"],
            "user": THEME["success"],
        }

    def append_chunk(self, chunk: str) -> None:
        """追加chunk"""
        self._chunks.append(chunk)
        self._content = "".join(self._chunks)
        self.update(self._render_content())

    def finalize(self, full_content: str) -> None:
        """完成消息"""
        self._content = full_content
        self.update(self._render_content())

    def _render_content(self) -> Text:
        color = self.colors.get(self.speaker.lower(), THEME["text_dim"])
        symbol = "◆" if self.speaker.lower() != "user" else "●"

        text = Text()
        text.append(f"{symbol} ", style=Style(color=color, bold=True))
        text.append(f"{self.role}: ", style=Style(color=THEME["text_dim"]))
        # 显示内容（最多300字）
        display_content = self._content[:300]
        text.append(display_content)
        if len(self._content) > 300:
            text.append("…", style=Style(color=THEME["text_dim"]))
        return text


# ========== 控制面板 ==========

class ControlPanel(Vertical):
    """控制面板 - 启动后只显示状态"""

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

    ControlPanel Static {{
        color: {THEME["text_dim"]};
        margin: 0 0 1 0;
    }}

    ControlPanel #status {{
        color: {THEME["accent_purple"]};
        text-style: bold;
    }}

    ControlPanel #topic-display {{
        color: {THEME["text"]};
        padding: 1;
        background: {THEME["bg_card"]};
    }}

    ControlPanel Button {{
        margin: 1 0;
        background: {THEME["bg_card"]};
    }}

    ControlPanel #stop-btn {{
        background: {THEME["error"]};
        color: {THEME["bg_dark"]};
    }}
    """

    def compose(self) -> ComposeResult:
        yield Label("状态")
        yield Static("待开始", id="status")

        yield Label("议题")
        yield Static("", id="topic-display")

        yield Label("角色")
        yield Static("", id="roles-display")

        yield Label("轮数")
        yield Static("0", id="round-stat")

        yield Button("停止", id="stop-btn", disabled=True)

    def update_status(self, status: str) -> None:
        self.query_one("#status", Static).update(status)

    def update_topic(self, topic: str) -> None:
        self.query_one("#topic-display", Static).update(topic[:50] + "…" if len(topic) > 50 else topic)

    def update_roles(self, preset: str) -> None:
        config = get_preset(preset)
        roles = f"◆ {config['debater1']['role']}\n◆ {config['debater2']['role']}"
        self.query_one("#roles-display", Static).update(roles)

    def update_round(self, round_num: int) -> None:
        self.query_one("#round-stat", Static).update(str(round_num))


# ========== 辩论显示区 ==========

class DebateView(VerticalScroll):
    """辩论显示区 - 流式输出"""

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
    """

    _current_streaming: StreamingMessage | None = None

    def compose(self) -> ComposeResult:
        yield Static(
            "◆ 辩论式 PRD 生成\n\n议题已设置 → 辩论进行中",
            id="welcome-text",
            classes="welcome",
        )

    def start_streaming(self, speaker: str, role: str) -> None:
        """开始新的流式消息"""
        # 移除欢迎文字
        try:
            welcome = self.query_one("#welcome-text")
            welcome.remove()
        except:
            pass

        # 创建新的流式消息组件
        self._current_streaming = StreamingMessage(speaker, role)
        self.mount(self._current_streaming)
        self.scroll_end(animate=False)

    def append_chunk(self, chunk: str) -> None:
        """追加流式chunk"""
        if self._current_streaming:
            self._current_streaming.append_chunk(chunk)

    def finalize_message(self, content: str) -> None:
        """完成当前消息"""
        if self._current_streaming:
            self._current_streaming.finalize(content)
            self._current_streaming = None

    def add_static_message(self, speaker: str, role: str, content: str) -> None:
        """添加静态消息（非流式）"""
        try:
            welcome = self.query_one("#welcome-text")
            welcome.remove()
        except:
            pass

        msg = StreamingMessage(speaker, role)
        msg.finalize(content)
        self.mount(msg)
        self.scroll_end(animate=False)


# ========== 状态面板 ==========

class StatusPanel(Vertical):
    """状态面板"""

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
    }}

    StatusPanel #prd-preview {{
        height: 10;
        background: {THEME["bg_card"]};
        border: solid {THEME["border"]};
        color: {THEME["text_dim"]};
    }}
    """

    def compose(self) -> ComposeResult:
        yield Label("PRD预览")
        from textual.widgets import TextArea
        yield TextArea(id="prd-preview", disabled=True)

    def update_prd(self, prd: str) -> None:
        preview = self.query_one("#prd-preview")
        preview.text = prd[:400] + "…" if len(prd) > 400 else prd


# ========== 主应用 ==========

class DebateTUIApp(App):
    """辩论式 PRD 生成 - 流式TUI"""

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
        Binding("q", "quit", "退出"),
        Binding("s", "stop", "停止"),
    ]

    TITLE = "◆ 辩论式 PRD 生成"
    SUB_TITLE = "流式输出"

    debate_running: reactive[bool] = reactive(False)
    debate_task: asyncio.Task | None = None

    # 启动参数（外部传入）
    preset: str = "pm_vs_dev"
    topic: str = "通用产品需求"

    def compose(self) -> ComposeResult:
        yield Header()
        yield ControlPanel()
        yield DebateView()
        yield StatusPanel()
        yield Footer()

    def on_mount(self) -> None:
        """启动时立即开始辩论"""
        self.action_start_debate()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "stop-btn":
            self.action_stop()

    def action_start_debate(self) -> None:
        """开始辩论"""
        if self.debate_running:
            return

        self.debate_running = True
        control = self.query_one(ControlPanel)
        control.update_status("● 辩论中")
        control.update_topic(self.topic)
        control.update_roles(self.preset)
        control.query_one("#stop-btn", Button).disabled = False

        self.debate_task = asyncio.create_task(self._run_debate())

    def action_stop(self) -> None:
        """停止"""
        if self.debate_task:
            self.debate_task.cancel()
        self._end_debate()

    async def _run_debate(self) -> None:
        """运行辩论 - 流式输出"""
        debate_view = self.query_one(DebateView)
        control = self.query_one(ControlPanel)
        status = self.query_one(StatusPanel)

        try:
            llm_config = LLMConfig.from_env()
            if not llm_config.api_key:
                debate_view.add_static_message("moderator", "Moderator", "◆ 请配置API Key")
                self._end_debate()
                return

            from autogen_ext.models.openai import OpenAIChatCompletionClient

            # 创建支持流式的客户端
            model_client = OpenAIChatCompletionClient(**llm_config.to_client_kwargs())

            settings = Settings(llm=llm_config, max_rounds=6)
            team = DebateTeam(preset=self.preset, model_client=model_client, settings=settings)

            preset_config = get_preset(self.preset)
            round_num = 0
            current_speaker = None
            current_role = None
            current_content_chunks = []

            debate_view.add_static_message("moderator", "Moderator", f"● 开始辩论")

            stream = team.run_stream(self.topic)

            async for event in stream:
                # 处理不同类型的事件
                event_type = type(event).__name__

                # 流式chunk事件
                if "StreamingChunk" in event_type or hasattr(event, 'chunk'):
                    speaker = getattr(event, 'source', current_speaker or 'unknown')
                    chunk = getattr(event, 'content', '') or getattr(event, 'chunk', '')

                    if chunk and isinstance(chunk, str):
                        # 如果是新发言者，开始新的流式消息
                        if speaker != current_speaker:
                            if current_speaker and current_content_chunks:
                                # 完成上一个消息
                                debate_view.finalize_message("".join(current_content_chunks))
                            current_speaker = speaker
                            current_role = self._get_role(speaker, preset_config)
                            current_content_chunks = []
                            debate_view.start_streaming(speaker, current_role)

                        current_content_chunks.append(chunk)
                        debate_view.append_chunk(chunk)

                # 完整消息事件
                elif hasattr(event, 'messages') and event.messages:
                    for msg in event.messages:
                        msg_source = getattr(msg, 'source', 'system')
                        msg_content = str(getattr(msg, 'content', ''))

                        if msg_content and not msg_content.startswith("["):
                            role = self._get_role(msg_source, preset_config)

                            # 如果有正在流式的消息，先完成它
                            if current_speaker:
                                debate_view.finalize_message(msg_content)
                                current_speaker = None
                                current_content_chunks = []

                            # 更新轮数
                            if "debater" in msg_source.lower():
                                round_num += 1
                                control.update_round(round_num)

                            # 检查PRD完成
                            if "[PRD_COMPLETE]" in msg_content:
                                prd = msg_content.replace("[PRD_COMPLETE]", "").strip()
                                status.update_prd(prd)
                                debate_view.add_static_message("moderator", "Moderator", "◆ PRD已生成")
                                self._end_debate()
                                return

                # TaskResult事件（结束）
                elif event_type == "TaskResult" or hasattr(event, 'stop_reason'):
                    if current_speaker and current_content_chunks:
                        debate_view.finalize_message("".join(current_content_chunks))
                    debate_view.add_static_message("moderator", "Moderator", "◆ 辩论结束")
                    self._end_debate()
                    return

        except asyncio.CancelledError:
            debate_view.add_static_message("moderator", "Moderator", "◆ 已停止")
            self._end_debate()

        except Exception as e:
            debate_view.add_static_message("moderator", "Moderator", f"◆ 错误: {str(e)[:100]}")
            self._end_debate()

    def _get_role(self, speaker: str, preset_config: dict) -> str:
        """获取角色名"""
        if "debater1" in speaker.lower():
            return preset_config["debater1"]["role"]
        elif "debater2" in speaker.lower():
            return preset_config["debater2"]["role"]
        elif "moderator" in speaker.lower():
            return "Moderator"
        return speaker

    def _end_debate(self) -> None:
        """结束"""
        self.debate_running = False
        self.debate_task = None

        control = self.query_one(ControlPanel)
        control.update_status("◆ 完成")
        control.query_one("#stop-btn", Button).disabled = True


def run_tui(preset: str = None, topic: str = None):
    """启动TUI - 支持外部传入参数

    Args:
        preset: 预设角色组合
        topic: 辩论议题
    """
    app = DebateTUIApp()

    # 设置启动参数
    if preset:
        app.preset = preset
    if topic:
        app.topic = topic

    app.run()


if __name__ == "__main__":
    run_tui()