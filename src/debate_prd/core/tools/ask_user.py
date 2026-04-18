"""AskUser Tool - 用户询问工具

提供Agent主动询问用户的能力：
- LLM可调用的function tool
- 支持选项式和开放式问答
- 异步等待用户响应
"""

from dataclasses import dataclass
from typing import Optional
import asyncio


@dataclass
class AskUserRequest:
    """用户询问请求"""
    question: str                # 询问的问题
    options: list[str] = None    # 可选选项（2-4个）
    allow_custom: bool = True    # 是否允许自定义回答


@dataclass
class AskUserResponse:
    """用户回答"""
    answer: str                  # 用户回答内容
    selected_option: int = -1    # 选择的选项索引
    is_custom: bool = False      # 是否自定义回答


class AskUserTool:
    """用户询问Tool - LLM可调用"""

    def __init__(self):
        self._latest_response: Optional[str] = None
        self._response_event: asyncio.Event = asyncio.Event()
        self._pending_request: Optional[AskUserRequest] = None

    def get_schema(self) -> dict:
        """返回Tool Schema（供LLM function calling）"""
        return {
            "type": "function",
            "function": {
                "name": "ask_user",
                "description": "询问用户问题以澄清需求。支持选项式问答和开放式问答。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "question": {
                            "type": "string",
                            "description": "要询问的问题"
                        },
                        "options": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "可选选项列表（2-4个）。如有选项，用户可以选择或输入自定义回答。",
                            "minItems": 2,
                            "maxItems": 4
                        },
                        "allow_custom": {
                            "type": "boolean",
                            "description": "是否允许用户输入自定义回答（默认true）",
                            "default": True
                        }
                    },
                    "required": ["question"]
                }
            }
        }

    async def execute(self, question: str, options: list[str] = None, allow_custom: bool = True) -> AskUserResponse:
        """执行Tool - 发送问题到TUI，等待用户回答

        Args:
            question: 问题文本
            options: 可选选项列表
            allow_custom: 是否允许自定义回答

        Returns:
            用户回答
        """
        self._pending_request = AskUserRequest(
            question=question,
            options=options,
            allow_custom=allow_custom,
        )
        self._latest_response = None
        self._response_event.clear()

        # 使用轮询机制等待用户回答（避免阻塞事件循环）
        # CLI 在 async for 循环中处理事件时会调用同步的 typer.prompt
        # 如果用 Event.wait() 会阻塞整个事件循环
        max_wait_seconds = 300  # 最长等待 5 分钟
        poll_interval = 0.1    # 每 100ms 检查一次
        waited = 0

        while not self._response_event.is_set() and waited < max_wait_seconds:
            await asyncio.sleep(poll_interval)
            waited += poll_interval

        if not self._response_event.is_set():
            # 超时，返回空回答
            return AskUserResponse(answer="", is_custom=True)

        response = self._latest_response

        # 解析回答
        if options and response:
            # 检查是否选择了选项
            try:
                selected_idx = int(response)
                if 0 <= selected_idx < len(options):
                    return AskUserResponse(
                        answer=options[selected_idx],
                        selected_option=selected_idx,
                        is_custom=False,
                    )
            except ValueError:
                pass

        return AskUserResponse(
            answer=response or "",
            is_custom=True,
        )

    def get_pending_request(self) -> Optional[AskUserRequest]:
        """获取当前待处理请求（由TUI调用以显示问题）"""
        return self._pending_request

    def submit_response(self, answer: str):
        """提交用户回答（由TUI调用）"""
        self._latest_response = answer
        self._response_event.set()

    def is_waiting(self) -> bool:
        """是否正在等待用户响应"""
        return not self._response_event.is_set()

    def clear(self):
        """清除状态"""
        self._latest_response = None
        self._response_event.clear()
        self._pending_request = None