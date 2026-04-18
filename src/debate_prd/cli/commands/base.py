"""命令注册机制 - 插件式架构"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ..session import InteractiveSession


class CommandHandler(ABC):
    """命令处理器基类"""

    name: str
    description: str
    usage: str

    @abstractmethod
    def execute(self, args: str, session: "InteractiveSession") -> None:
        """执行命令

        Args:
            args: 命令参数字符串
            session: 交互会话状态
        """
        raise NotImplementedError


class CommandRegistry:
    """命令注册中心"""

    def __init__(self):
        self._commands: dict[str, CommandHandler] = {}

    def register(self, handler: CommandHandler) -> None:
        """注册命令处理器"""
        self._commands[handler.name] = handler

    def get(self, name: str) -> CommandHandler | None:
        """获取命令处理器"""
        return self._commands.get(name)

    def list_all(self) -> list[str]:
        """列出所有命令名称"""
        return list(self._commands.keys())

    def get_all_handlers(self) -> list[CommandHandler]:
        """获取所有处理器"""
        return list(self._commands.values())


def parse_input(user_input: str) -> tuple[str, str]:
    """解析用户输入

    Returns:
        (command_name, args) 或 ("text", user_input)
    """
    if not user_input.startswith("/"):
        return ("text", user_input)

    parts = user_input[1:].split(maxsplit=1)
    command = parts[0].lower()
    args = parts[1] if len(parts) > 1 else ""

    return (command, args)
