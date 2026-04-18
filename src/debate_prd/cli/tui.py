"""辩论式 PRD 生成系统 - TUI 界面（Rosé Pine 主题）

遵循 DESIGH.md 设计规范，使用 Rosé Pine 颜色系统。
支持完整流程：问答 → 辩论 → 引导 → PRD生成
"""

from textual.app import App, ComposeResult
from textual.widgets import Header, Footer, Static, Button, Input, Label, RichLog, ProgressBar, MarkdownViewer
from textual.containers import Container, Vertical, Horizontal, ScrollableContainer
from textual.binding import Binding
from textual.reactive import reactive
from textual.screen import Screen, ModalScreen
from textual.messages import Message
import asyncio

from ..config.presets import get_preset, list_presets
from ..config.settings import LLMConfig, Settings
from ..core.debate_loop import run_debate_stream, ModeratorState
from ..core.tools import AskUserTool


# === 颜色常量（消除魔法值） ===

DEBATER_COLORS = {
    "debater1": "#c4a7e7",  # Rosé Pine: Iris (紫色调)
    "debater2": "#ebbcba",  # Rosé Pine: Love (粉色调)
}


def _get_debater_color(speaker: str) -> str:
    """获取辩论者颜色（消除重复）

    Args:
        speaker: 发言者名称（debater1、debater2等）

    Returns:
        颜色代码
    """
    return DEBATER_COLORS.get(speaker.lower(), "#e6edf3")


# === 自定义事件 ===

class QuestionAnswered(Message):
    """问答回答事件"""
    category: str
    answer: str

    def __init__(self, category: str, answer: str) -> None:
        super().__init__()
        self.category = category
        self.answer = answer


class TopicSubmitted(Message):
    """议题提交事件"""
    topic: str

    def __init__(self, topic: str) -> None:
        super().__init__()
        self.topic = topic


class ConfigSaved(Message):
    """配置保存事件"""
    api_key: str
    base_url: str
    model: str

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        super().__init__()
        self.api_key = api_key
        self.base_url = base_url
        self.model = model


# === Rosé Pine 主题 CSS ===
# 所有颜色必须为硬编码十六进制，Textual CSS 不支持变量

CSS = """
/* === 全局背景 === */
Screen {
    background: #191724;
    color: #e0def4;
}

/* === 布局层级 === */
.main-area {
    layout: horizontal;
    height: 1fr;
    background: #191724;
}

/* 左侧面板 (Z-Index 1: Surface) */
.left-panel {
    width: 24;
    dock: left;
    padding: 1 2;
    background: #1f1d2e;
    border-right: solid #6e6a86;
}

/* 中间辩论区 (Z-Index 0: Base) */
.center-panel {
    width: 1fr;
    padding: 1;
    background: #191724;
}

/* 右侧 PRD 预览 (Z-Index 1: Surface) */
.right-panel {
    width: 38;
    dock: right;
    padding: 1 2;
    background: #1f1d2e;
    border-left: solid #6e6a86;
}

/* === 文本样式 === */
Static {
    color: #e0def4;
}

.label {
    color: #c4a7e7;
    text-style: bold;
    margin-bottom: 1;
}

.status-running {
    color: #f6c177;
}

.status-complete {
    color: #31748f;
}

.status-error {
    color: #eb6f92;
}

.status-idle {
    color: #908caa;
}

/* === 按钮样式 === */
Button {
    width: 100%;
    margin: 1;
    background: #1f1d2e;
    color: #e0def4;
    border: solid #6e6a86;
}

Button:focus {
    background: #26233a;
    border: solid #c4a7e7;
    color: #c4a7e7;
}

Button:hover {
    background: #26233a;
}

Button:disabled {
    color: #908caa;
    background: #191724;
}

/* === 进度条 === */
ProgressBar {
    background: #6e6a86;
}

ProgressBar > .bar--bar {
    background: #c4a7e7;
}

/* === 输入框 === */
Input {
    background: #1f1d2e;
    color: #e0def4;
    border: solid #6e6a86;
}

Input:focus {
    border: solid #c4a7e7;
}

Input .placeholder {
    color: #908caa;
}

/* === RichLog === */
RichLog {
    background: #191724;
    color: #e0def4;
}

/* === Header/Footer === */
Header {
    background: #1f1d2e;
    color: #c4a7e7;
}

Footer {
    background: #1f1d2e;
    color: #e0def4;
}

Footer > .key {
    color: #c4a7e7;
}

Footer > .description {
    color: #908caa;
}

/* === 弹窗/面板样式 === */
.modal-container {
    align: center middle;
    background: #191724;
}

.modal-panel {
    width: 50;
    height: auto;
    background: #1f1d2e;
    border: solid #c4a7e7;
    padding: 2;
}

.modal-title {
    color: #c4a7e7;
    text-style: bold;
    margin-bottom: 1;
}

.modal-hint {
    color: #908caa;
    margin-top: 1;
}

.config-row {
    layout: horizontal;
    height: 3;
    margin: 1;
}

.config-label {
    width: 16;
    color: #e0def4;
}

.config-input {
    width: 1fr;
}

.modal-buttons {
    layout: horizontal;
    height: 3;
    margin-top: 2;
}

/* === 边框聚焦效果 === */
.panel-inactive {
    border: solid #6e6a86;
}

.panel-active:focus-within {
    border: solid #c4a7e7;
}
"""


class OptionsDialog(ModalScreen):
    """选项式问答弹窗"""

    CSS = """
    OptionsDialog {
        align: center middle;
        background: #191724;
    }

    .options-container {
        width: 60;
        height: auto;
        background: #1f1d2e;
        border: solid #c4a7e7;
        padding: 2;
    }

    .options-question {
        color: #e0def4;
        margin-bottom: 1;
    }

    .options-input {
        width: 1fr;
        margin: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "custom", "自定义回答"),
    ]

    def __init__(self, question: str, options: list[str], allow_custom: bool = True):
        super().__init__()
        self.question = question
        self.options = options
        self.allow_custom = allow_custom

    def compose(self) -> ComposeResult:
        with Container(classes="options-container"):
            yield Static(f"[Moderator]: {self.question}", classes="options-question")
            for i, opt in enumerate(self.options):
                yield Button(f"[{i+1}] {opt}", id=f"opt-{i}")
            if self.allow_custom:
                yield Input(placeholder="输入自定义回答...", id="custom-input", classes="options-input")
                yield Button("确认自定义", id="custom-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id and event.button.id.startswith("opt-"):
            idx = int(event.button.id.replace("opt-", ""))
            self.dismiss((idx, self.options[idx]))
        elif event.button.id == "custom-btn":
            answer = self.query_one("#custom-input", Input).value.strip()
            self.dismiss((-1, answer))

    def action_custom(self) -> None:
        if self.allow_custom:
            answer = self.query_one("#custom-input", Input).value.strip()
            self.dismiss((-1, answer))
        else:
            self.dismiss((0, self.options[0]))


class QuestionDialog(ModalScreen):
    """问答弹窗"""

    CSS = """
    QuestionDialog {
        align: center middle;
        background: #191724;
    }

    .question-container {
        width: 60;
        height: auto;
        background: #1f1d2e;
        border: solid #c4a7e7;
        padding: 2;
    }

    .question-label {
        color: #c4a7e7;
        text-style: bold;
        margin-bottom: 1;
    }

    .question-text {
        color: #e0def4;
        margin-bottom: 1;
    }

    .question-input {
        width: 1fr;
        margin: 1;
    }

    .question-buttons {
        layout: horizontal;
        height: 3;
        margin-top: 2;
    }
    """

    BINDINGS = [
        Binding("escape", "skip", "跳过"),
        Binding("enter", "confirm", "确认"),
    ]

    def __init__(self, question: str, category: str, allow_skip: bool = True):
        super().__init__()
        self.question = question
        self.category = category
        self.allow_skip = allow_skip

    def compose(self) -> ComposeResult:
        with Container(classes="question-container"):
            yield Static(f"【{self.category}】", classes="question-label")
            yield Static(self.question, classes="question-text")
            yield Input(placeholder="请输入回答...", id="question-input", classes="question-input")
            with Horizontal(classes="question-buttons"):
                yield Button("确认", id="confirm-btn", variant="primary")
                if self.allow_skip:
                    yield Button("跳过", id="skip-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.action_confirm()
        elif event.button.id == "skip-btn":
            self.action_skip()

    def action_confirm(self) -> None:
        answer = self.query_one("#question-input", Input).value.strip()
        self.dismiss((self.category, answer))

    def action_skip(self) -> None:
        self.dismiss((self.category, ""))


class GuidanceDialog(ModalScreen):
    """引导确认弹窗"""

    CSS = """
    GuidanceDialog {
        align: center middle;
        background: #191724;
    }

    .guidance-container {
        width: 60;
        height: auto;
        background: #1f1d2e;
        border: solid #f6c177;
        padding: 2;
    }

    .guidance-label {
        color: #f6c177;
        text-style: bold;
        margin-bottom: 1;
    }

    .guidance-text {
        color: #e0def4;
        margin-bottom: 1;
    }

    .guidance-buttons {
        layout: horizontal;
        height: 3;
        margin-top: 2;
    }
    """

    def __init__(self, guidance: str, options: list[str]):
        super().__init__()
        self.guidance = guidance
        self.options = options

    def compose(self) -> ComposeResult:
        with Container(classes="guidance-container"):
            yield Static("[Moderator引导]", classes="guidance-label")
            yield Static(self.guidance[:400], classes="guidance-text")
            with Vertical(classes="guidance-buttons"):
                for i, opt in enumerate(self.options):
                    yield Button(opt, id=f"opt-{i}")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        selected_idx = int(event.button.id.replace("opt-", ""))
        self.dismiss(self.options[selected_idx])


class TopicInputScreen(Screen):
    """议题输入面板"""

    CSS = """
    TopicInputScreen {
        align: center middle;
        background: #191724;
    }

    .topic-container {
        width: 55;
        height: auto;
        background: #1f1d2e;
        border: solid #c4a7e7;
        padding: 2;
    }

    .topic-title {
        color: #c4a7e7;
        text-style: bold;
        margin-bottom: 1;
    }

    .topic-input {
        width: 1fr;
        height: 3;
        margin: 1;
    }

    .topic-hint {
        color: #908caa;
        margin-top: 1;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "取消"),
        Binding("enter", "confirm", "确认"),
    ]

    def compose(self) -> ComposeResult:
        with Container(classes="topic-container"):
            yield Static("输入辩论议题", classes="topic-title")
            yield Input(
                placeholder="例如: 开发用户登录系统...",
                id="topic-input",
                classes="topic-input"
            )
            yield Static("按 Enter 确认，Esc 取消", classes="topic-hint")
            with Horizontal(classes="modal-buttons"):
                yield Button("确认", id="confirm-btn", variant="primary")
                yield Button("取消", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "confirm-btn":
            self.action_confirm()
        elif event.button.id == "cancel-btn":
            self.action_close()

    def action_confirm(self) -> None:
        topic = self.query_one("#topic-input", Input).value.strip()
        if topic:
            self.app.post_message(TopicSubmitted(topic))
            self.app.pop_screen()

    def action_close(self) -> None:
        self.app.pop_screen()


class ConfigScreen(Screen):
    """配置面板"""

    CSS = """
    ConfigScreen {
        align: center middle;
        background: #191724;
    }

    .config-container {
        width: 60;
        height: auto;
        background: #1f1d2e;
        border: solid #c4a7e7;
        padding: 2;
    }

    .config-title {
        color: #c4a7e7;
        text-style: bold;
        margin-bottom: 1;
    }

    .config-row {
        layout: horizontal;
        height: 3;
        margin: 1;
    }

    .config-label {
        width: 16;
        color: #e0def4;
    }

    .config-input {
        width: 1fr;
    }

    .config-buttons {
        layout: horizontal;
        height: 3;
        margin-top: 2;
    }
    """

    BINDINGS = [
        Binding("escape", "close", "关闭"),
    ]

    def compose(self) -> ComposeResult:
        with Container(classes="config-container"):
            yield Static("配置设置", classes="config-title")

            with Horizontal(classes="config-row"):
                yield Label("API Key:", classes="config-label")
                yield Input(placeholder="输入 API Key...", id="api-key")

            with Horizontal(classes="config-row"):
                yield Label("Base URL:", classes="config-label")
                yield Input(value="https://api.openai.com/v1", id="base-url")

            with Horizontal(classes="config-row"):
                yield Label("Model:", classes="config-label")
                yield Input(value="gpt-4o-mini", id="model")

            with Horizontal(classes="config-buttons"):
                yield Button("保存", id="save-btn", variant="primary")
                yield Button("取消", id="cancel-btn")

    def on_mount(self) -> None:
        """加载当前配置"""
        config = LLMConfig.from_env()
        if config.api_key:
            self.query_one("#api-key", Input).value = config.api_key[:20] + "..."
        self.query_one("#base-url", Input).value = config.base_url
        self.query_one("#model", Input).value = config.model

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "save-btn":
            self.action_save()
        elif event.button.id == "cancel-btn":
            self.action_close()

    def action_save(self) -> None:
        """保存配置"""
        api_key = self.query_one("#api-key", Input).value
        base_url = self.query_one("#base-url", Input).value
        model = self.query_one("#model", Input).value
        self.app.post_message(ConfigSaved(api_key, base_url, model))
        self.app.pop_screen()

    def action_close(self) -> None:
        self.app.pop_screen()


class DebateApp(App):
    """辩论式 PRD 生成 - TUI (Rosé Pine 主题)"""

    CSS = CSS

    BINDINGS = [
        Binding("b", "start_debate", "开始"),
        Binding("t", "input_topic", "议题"),
        Binding("c", "config", "配置"),
        Binding("p", "toggle_presets", "预设"),
        Binding("s", "stop", "停止"),
        Binding("q", "quit", "退出"),
    ]

    TITLE = "辩论式 PRD 生成"
    SUB_TITLE = "Rosé Pine Theme"

    debate_running: reactive[bool] = reactive(False)
    debate_task: asyncio.Task | None = None

    preset: str = "pm_vs_dev"
    topic: str = "产品需求"
    rounds: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        yield Header()

        with Container(classes="main-area"):
            # 左侧状态面板
            with Vertical(classes="left-panel panel-inactive"):
                yield Static("状态", classes="label")
                yield Static("待开始", id="status", classes="status-idle")

                yield Static("议题", classes="label")
                yield Static(self.topic[:22], id="topic")

                yield Static("轮数", classes="label")
                yield Static("0", id="rounds")

                yield Static("预设", classes="label")
                yield Static(self.preset, id="preset")

                yield ProgressBar(total=6, id="progress")
                yield Button("停止", id="stop-btn", disabled=True)

            # 中间辩论区
            with ScrollableContainer(classes="center-panel"):
                yield RichLog(id="debate-log", wrap=True)

            # 右侧 PRD 预览
            with ScrollableContainer(classes="right-panel panel-inactive"):
                yield Static("PRD 预览", classes="label")
                yield MarkdownViewer("等待辩论结束...", id="prd-preview")

        yield Footer()

    def on_mount(self) -> None:
        """初始化"""
        self.query_one("#topic").update(self.topic[:22])
        self.query_one("#preset").update(self.preset)

        log = self.query_one("#debate-log", RichLog)
        log.write("[#c4a7e7]● 辩论式 PRD 生成系统[/#c4a7e7]")
        log.write("[#e0def4]按 [B] 开始辩论，[T] 编辑议题，[C] 配置，[P] 切换预设[/#e0def4]")

    def on_topic_submitted(self, event: TopicSubmitted) -> None:
        """处理议题提交"""
        self.topic = event.topic
        self.query_one("#topic").update(event.topic[:22])
        self.query_one("#debate-log", RichLog).write(f"[#9ccfd8]议题已设置: {event.topic}[/#9ccfd8]")

    def on_config_saved(self, event: ConfigSaved) -> None:
        """处理配置保存"""
        log = self.query_one("#debate-log", RichLog)
        log.write(f"[#31748f]配置已保存[/#31748f]")
        log.write(f"[#908caa]  Model: {event.model}[/#908caa]")
        log.write(f"[#908caa]  Base URL: {event.base_url}[/#908caa]")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "stop-btn":
            self.action_stop()

    def action_start_debate(self) -> None:
        """开始辩论"""
        if self.debate_running:
            return

        if not self.topic or self.topic == "产品需求":
            self.push_screen(TopicInputScreen())
            return

        self.debate_running = True
        self.query_one("#status").update("● 辩论中")
        self.query_one("#status").set_classes("status-running")
        self.query_one("#stop-btn").disabled = False
        self.debate_task = asyncio.create_task(self._run_debate())

    def action_input_topic(self) -> None:
        """输入议题"""
        self.push_screen(TopicInputScreen())

    def action_config(self) -> None:
        """打开配置面板"""
        self.push_screen(ConfigScreen())

    def action_stop(self) -> None:
        """停止辩论"""
        if self.debate_task:
            self.debate_task.cancel()
        self._end_debate()

    def action_toggle_presets(self) -> None:
        """切换预设"""
        presets = list_presets()
        current_idx = presets.index(self.preset) if self.preset in presets else 0
        next_idx = (current_idx + 1) % len(presets)
        self.preset = presets[next_idx]
        self.query_one("#preset").update(self.preset)
        log = self.query_one("#debate-log", RichLog)
        preset_config = get_preset(self.preset)
        log.write(f"[#c4a7e7]预设切换: {self.preset}[/#c4a7e7]")
        log.write(f"[#908caa]  {preset_config['debater1']['role']} vs {preset_config['debater2']['role']}[/#908caa]")

    async def _run_debate(self) -> None:
        """运行完整辩论流程（问答 + 辩论 + 引导）"""
        log = self.query_one("#debate-log", RichLog)
        progress = self.query_one("#progress", ProgressBar)

        try:
            llm_config = LLMConfig.from_env()
            if not llm_config.api_key:
                log.write("[#eb6f92]◆ 请配置 API Key[/#eb6f92]")
                log.write("[#908caa]  按 [C] 打开配置面板[/#908caa]")
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

            log.write(f"[#c4a7e7]● 开始完整流程[/#c4a7e7]")
            log.write(f"[#9ccfd8]议题: {self.topic}[/#9ccfd8]")

            # 创建AskUserTool
            ask_user_tool = AskUserTool()

            stream = run_debate_stream(
                topic=self.topic,
                llm_client=client,
                preset=self.preset,
                settings=settings,
                ask_user_tool=ask_user_tool,
            )

            self.rounds = 0
            moderator_state = None
            current_message_buffer = {}  # 用于流式输出缓冲
            current_role = ""  # 当前发言角色

            async for event in stream:
                event_type = event.get("type", "")

                # 处理阶段切换
                if event_type == "phase_start":
                    phase = event["phase"]
                    log.write(f"[#c4a7e7]━━━ 阶段: {phase} ━━━[/#c4a7e7]")
                    self.query_one("#status").update(f"● {phase}")

                # 处理子阶段切换（自由辩论模式）
                elif event_type == "sub_phase":
                    sub_phase = event["phase"]
                    if sub_phase == "publish_view":
                        log.write(f"[#f6c177]◆ 双方并发发表看法[/#f6c177]")
                    elif sub_phase == "free_debate":
                        log.write(f"[#f6c177]◆ 进入自由辩论[/#f6c177]")

                # 处理问答提示
                elif event_type == "question_prompt":
                    category = event["category"]
                    question = event["content"]

                    # 显示问答弹窗
                    dialog = QuestionDialog(question, category)
                    result = await self.push_screen(dialog)

                    category_answer, answer = result if result else (category, "")
                    log.write(f"[#9ccfd8]【{category}】[/#9ccfd8]: {answer or '(跳过)'}")

                    # 提交回答到Tool
                    ask_user_tool.submit_response(answer)

                # 处理 Token 级流式输出
                elif event_type == "token":
                    delta = event["delta"]
                    role = event["role"]
                    speaker = event["speaker"]

                    # 确定角色颜色
                    role_color = _get_debater_color(speaker)

                    # 首次出现新角色时初始化缓冲区并写入前缀
                    if role != current_role:
                        current_role = role
                        current_message_buffer[role] = ""  # 只累积纯文本内容
                        log.write(f"[{role_color}]【{role}】[/{role_color}]: ", with_newline=False)

                    # 累积 token（用于后续完整消息显示）
                    current_message_buffer[role] += delta

                    # 实时显示token（只显示新增的delta）
                    log.write(f"[{role_color}]{delta}[/{role_color}]", with_newline=False)

                # 处理消息完成
                elif event_type == "message_complete":
                    speaker = event["speaker"]
                    role = event["role"]
                    content = event["content"]

                    # 使用角色颜色
                    role_color = _get_debater_color(speaker)

                    # 写入完整消息到 RichLog
                    log.write(f"[{role_color}]【{role}】[/{role_color}]: {content}")
                    log.write("[dim]" + "-" * 40 + "[/dim]")

                    # 清空缓冲区
                    if role in current_message_buffer:
                        del current_message_buffer[role]
                    current_role = ""

                    if "debater" in speaker.lower():
                        self.rounds += 1
                        progress.update(self.rounds)
                        self.query_one("#rounds").update(str(self.rounds))

                # 处理Tool调用（Agent驱动）
                elif event_type == "tool_call":
                    tool = event["tool"]
                    question = event["question"]
                    options = event.get("options", [])
                    allow_custom = event.get("allow_custom", True)

                    log.write(f"[#c4a7e7][Moderator提问][/#c4a7e7]")
                    log.write(f"[#e0def4]{question}[/#e0def4]")

                    if options:
                        # 显示选项
                        for i, opt in enumerate(options):
                            log.write(f"[#908caa]  [{i+1}] {opt}[/#908caa]")
                        if allow_custom:
                            log.write(f"[#908caa]  [其他] 输入自定义回答[/#908caa]")

                        # 选项式弹窗
                        dialog = OptionsDialog(question, options, allow_custom)
                        result = await self.push_screen(dialog)

                        if isinstance(result, tuple):
                            idx, answer = result
                            log.write(f"[#9ccfd8]用户选择: {answer if answer else f'选项{idx+1}'}[/#9ccfd8]")
                            ask_user_tool.submit_response(str(idx) if idx >= 0 else answer)
                        else:
                            log.write(f"[#9ccfd8]用户回答: {result}[/#9ccfd8]")
                            ask_user_tool.submit_response(result)
                    else:
                        # 开放式问答
                        dialog = QuestionDialog(question, "请回答", allow_skip=allow_custom)
                        result = await self.push_screen(dialog)

                        category, answer = result if result else ("", "")
                        log.write(f"[#9ccfd8]用户回答: {answer or '(跳过)'}[/#9ccfd8]")
                        ask_user_tool.submit_response(answer)

                # 处理 Moderator 协调消息
                elif event_type == "moderator":
                    action = event.get("action", "")
                    content = event.get("content", "")
                    # Moderator 消息用绿色区分
                    log.write(f"[#31748f]● Moderator:[/#31748f] {content}")

                # 处理引导消息
                elif event_type == "guidance":
                    guidance = event["content"]
                    log.write(f"[#f6c177][Moderator引导][/#f6c177]")
                    log.write(f"[#908caa]{guidance}[/#908caa]")

                # 处理Tool请求
                elif event_type == "tool_request":
                    question = event["question"]
                    context = event.get("context", "")
                    options = event.get("options", [])

                    log.write(f"[#f6c177]◆ 需要用户决策[/#f6c177]")
                    log.write(f"[#908caa]{question}[/#908caa]")

                    # 显示引导弹窗
                    if options:
                        dialog = GuidanceDialog(context, options)
                        result = await self.push_screen(dialog)
                        log.write(f"[#9ccfd8]用户选择: {result}[/#9ccfd8]")
                        ask_user_tool.submit_response(result)

                # 处理PRD基础版生成
                elif event_type == "prd_base_generated":
                    prd_base = event["content"]
                    log.write(f"[#31748f]◆ PRD基础版已生成[/#31748f]")
                    # 使用 MarkdownViewer 渲染
                    prd_preview = self.query_one("#prd-preview", MarkdownViewer)
                    prd_preview.document.update(prd_base)

                # 处理辩论完成
                elif event_type == "debate_complete":
                    prd = event["prd"]
                    # 使用 MarkdownViewer 渲染完整 PRD
                    prd_preview = self.query_one("#prd-preview", MarkdownViewer)
                    prd_preview.document.update(prd)
                    log.write(f"[#31748f]◆ 辩论结束[/#31748f]")
                    log.write(f"[#908caa]轮数: {event['rounds']}[/#908caa]")
                    log.write(f"[#908caa]原因: {event['reason']}[/#908caa]")
                    self._end_debate()
                    return

        except asyncio.CancelledError:
            log.write("[#f6c177]◆ 已停止[/#f6c177]")
            self._end_debate()

        except Exception as e:
            log.write(f"[#eb6f92]◆ 错误: {str(e)[:100]}[/#eb6f92]")
            self._end_debate()

    def _end_debate(self) -> None:
        """结束辩论"""
        self.debate_running = False
        self.debate_task = None
        self.query_one("#status").update("◆ 完成")
        self.query_one("#status").set_classes("status-complete")
        self.query_one("#stop-btn").disabled = True


def run_tui(preset: str = None, topic: str = None):
    """启动 TUI"""
    app = DebateApp()
    if preset:
        app.preset = preset
    if topic:
        app.topic = topic
    app.run()


if __name__ == "__main__":
    run_tui()