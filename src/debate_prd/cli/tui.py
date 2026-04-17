"""辩论式 PRD 生成系统 - TUI 界面（简化版）

确保兼容性和文字可见性
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Button
from textual.containers import Container, Vertical, Horizontal
from textual.binding import Binding
from textual.reactive import reactive
from rich.text import Text
from rich.style import Style
import asyncio
import os

from ..config.presets import get_preset
from ..config.settings import LLMConfig, Settings
from ..core.debate_loop import run_debate_stream


class DebateApp(App):
    """辩论式PRD生成 - TUI"""

    CSS = """
    Screen {
        layout: vertical;
    }

    .main-area {
        layout: horizontal;
        height: 1fr;
    }

    .left-panel {
        width: 20;
        dock: left;
        padding: 1;
    }

    .center-panel {
        width: 1fr;
        padding: 1;
    }

    .right-panel {
        width: 30;
        dock: right;
        padding: 1;
    }

    Static {
        color: #e6edf3;
    }

    .label {
        color: #58a6ff;
        text-style: bold;
    }

    .status {
        color: #3fb950;
    }

    .message {
        color: #e6edf3;
        margin: 1 0;
    }

    Button {
        width: 100%;
        margin: 1;
    }
    """

    BINDINGS = [
        Binding("b", "start_debate", "开始"),
        Binding("s", "stop", "停止"),
        Binding("q", "quit", "退出"),
    ]

    TITLE = "辩论式 PRD 生成"

    debate_running: reactive[bool] = reactive(False)
    debate_task: asyncio.Task | None = None

    preset: str = "pm_vs_dev"
    topic: str = "产品需求"

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(classes="main-area"):
            # 左侧面板
            with Vertical(classes="left-panel"):
                yield Static("状态", classes="label")
                yield Static("待开始", id="status", classes="status")
                yield Static("议题", classes="label")
                yield Static(self.topic[:25], id="topic")
                yield Static("轮数", classes="label")
                yield Static("0", id="rounds")
                yield Static("预设", classes="label")
                yield Static(self.preset, id="preset")
                yield Button("停止", id="stop-btn", disabled=True)

            # 中间辩论区
            with Vertical(classes="center-panel"):
                yield Static(
                    f"● 辩论式PRD生成\n议题: {self.topic}\n预设: {self.preset}\n\n按 [B] 开始辩论",
                    id="debate-area",
                    classes="message"
                )

            # 右侧PRD预览
            with Vertical(classes="right-panel"):
                yield Static("PRD 预览", classes="label")
                yield Static("等待辩论结束...", id="prd-preview")

        yield Footer()

    def on_mount(self) -> None:
        """初始化"""
        self.query_one("#topic").update(self.topic[:25])
        self.query_one("#preset").update(self.preset)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "stop-btn":
            self.action_stop()

    def action_start_debate(self) -> None:
        """开始辩论"""
        if self.debate_running:
            return

        self.debate_running = True
        self.query_one("#status").update("● 辩论中")
        self.query_one("#stop-btn").disabled = False
        self.debate_task = asyncio.create_task(self._run_debate())

    def action_stop(self) -> None:
        """停止"""
        if self.debate_task:
            self.debate_task.cancel()
        self._end_debate()

    async def _run_debate(self) -> None:
        """运行辩论"""
        debate_area = self.query_one("#debate-area")
        rounds_display = self.query_one("#rounds")
        prd_preview = self.query_one("#prd-preview")

        try:
            llm_config = LLMConfig.from_env()
            if not llm_config.api_key:
                debate_area.update("◆ 请配置API Key")
                self._end_debate()
                return

            from openai import AsyncOpenAI
            client = AsyncOpenAI(
                api_key=llm_config.api_key,
                base_url=llm_config.base_url,
            )
            client.model = llm_config.model

            settings = Settings(max_rounds=6)
            preset_config = get_preset(self.preset)

            debate_area.update(f"● 辩论开始\n{preset_config['debater1']['role']} vs {preset_config['debater2']['role']}")

            stream = run_debate_stream(
                topic=self.topic,
                llm_client=client,
                preset=self.preset,
                settings=settings,
            )

            messages = []
            rounds = 0

            async for event in stream:
                event_type = event.get("type", "")

                if event_type == "message":
                    speaker = event["speaker"]
                    role = event["role"]
                    content = event["content"][:150]

                    messages.append(f"\n【{role}】{content}")

                    # 显示最近3条消息
                    display = "● 辩论进行中\n" + "\n".join(messages[-3:])
                    debate_area.update(display)

                    if "debater" in speaker.lower():
                        rounds += 1
                        rounds_display.update(str(rounds))

                elif event_type == "debate_complete":
                    prd = event["prd"]
                    prd_preview.update(prd[:400])
                    debate_area.update(f"◆ 辩论结束\n轮数: {event['rounds']}\n原因: {event['reason']}")
                    self._end_debate()
                    return

        except asyncio.CancelledError:
            debate_area.update("◆ 已停止")
            self._end_debate()

        except Exception as e:
            debate_area.update(f"◆ 错误: {str(e)[:100]}")
            self._end_debate()

    def _end_debate(self) -> None:
        """结束"""
        self.debate_running = False
        self.debate_task = None
        self.query_one("#status").update("◆ 完成")
        self.query_one("#stop-btn").disabled = True


def run_tui(preset: str = None, topic: str = None):
    """启动TUI"""
    app = DebateApp()
    if preset:
        app.preset = preset
    if topic:
        app.topic = topic
    app.run()


if __name__ == "__main__":
    run_tui()