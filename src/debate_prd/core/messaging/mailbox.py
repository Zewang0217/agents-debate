"""消息传递机制 - 基于Claude Code的teammateMailbox设计

简化实现：
- 支持代理间发送文本消息
- 支持广播（to: "*"）
- 内存队列（非持久化）
"""

from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime
import asyncio
from collections import defaultdict


@dataclass
class DebateMessage:
    """辩论消息"""
    from_agent: str  # 发送者
    to_agent: str    # 接收者（"*"表示广播）
    content: str     # 消息内容
    timestamp: datetime = field(default_factory=datetime.now)
    message_type: str = "text"  # text, consensus, disagreement

    def is_broadcast(self) -> bool:
        return self.to_agent == "*"


@dataclass
class Mailbox:
    """消息邮箱 - 每个Agent的收件箱"""
    owner: str  # 邮箱所有者
    pending_messages: list[DebateMessage] = field(default_factory=list)
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def receive(self, message: DebateMessage) -> None:
        """接收消息"""
        async with self.lock:
            self.pending_messages.append(message)

    async def get_messages(self) -> list[DebateMessage]:
        """获取所有待处理消息"""
        async with self.lock:
            messages = list(self.pending_messages)
            self.pending_messages.clear()
            return messages

    async def has_pending(self) -> bool:
        """是否有待处理消息"""
        async with self.lock:
            return len(self.pending_messages) > 0


class MessageRouter:
    """消息路由器 - 管理所有Agent的邮箱"""

    def __init__(self):
        self._mailboxes: dict[str, Mailbox] = defaultdict(lambda: Mailbox(owner="unknown"))

    def register_agent(self, agent_name: str) -> Mailbox:
        """注册Agent并返回其邮箱"""
        mailbox = Mailbox(owner=agent_name)
        self._mailboxes[agent_name] = mailbox
        return mailbox

    async def send_message(self, message: DebateMessage) -> None:
        """发送消息到目标邮箱"""
        if message.is_broadcast():
            # 广播：发送给所有Agent（除了发送者）
            for agent_name, mailbox in self._mailboxes.items():
                if agent_name != message.from_agent:
                    await mailbox.receive(message)
        else:
            # 定向发送
            if message.to_agent in self._mailboxes:
                await self._mailboxes[message.to_agent].receive(message)
            else:
                # 目标不存在，记录警告但不阻塞
                print(f"[Warning] Agent '{message.to_agent}' not registered")

    async def get_mailbox(self, agent_name: str) -> Mailbox:
        """获取Agent的邮箱"""
        return self._mailboxes[agent_name]


# 全局消息路由器实例
_global_router: MessageRouter | None = None


def get_message_router() -> MessageRouter:
    """获取全局消息路由器"""
    global _global_router
    if _global_router is None:
        _global_router = MessageRouter()
    return _global_router


def reset_message_router() -> None:
    """重置全局消息路由器（用于新的辩论会话）"""
    global _global_router
    _global_router = None


# ========== 便捷函数 ==========

async def send_to_agent(
    from_agent: str,
    to_agent: str,
    content: str,
    message_type: str = "text"
) -> None:
    """发送消息给特定Agent"""
    router = get_message_router()
    message = DebateMessage(
        from_agent=from_agent,
        to_agent=to_agent,
        content=content,
        message_type=message_type
    )
    await router.send_message(message)


async def broadcast(
    from_agent: str,
    content: str,
    message_type: str = "text"
) -> None:
    """广播消息给所有Agent"""
    router = get_message_router()
    message = DebateMessage(
        from_agent=from_agent,
        to_agent="*",
        content=content,
        message_type=message_type
    )
    await router.send_message(message)


async def check_messages(agent_name: str) -> list[DebateMessage]:
    """检查Agent的消息"""
    router = get_message_router()
    mailbox = await router.get_mailbox(agent_name)
    return await mailbox.get_messages()