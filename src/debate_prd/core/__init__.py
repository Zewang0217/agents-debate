"""辩论核心模块"""

from .memory.agent_memory import (
    MemoryScope,
    load_agent_memory,
    save_agent_memory,
    build_memory_prompt,
)

from .messaging.mailbox import (
    DebateMessage,
    Mailbox,
    MessageRouter,
    get_message_router,
    reset_message_router,
    send_to_agent,
    broadcast,
)

from .spawn.debater_agent import (
    DebaterConfig,
    DebaterAgent,
    create_debater_pair,
)

from .debate_loop import (
    DebateState,
    DebateModerator,
    run_debate,
    run_debate_stream,
)


__all__ = [
    # Memory
    "MemoryScope",
    "load_agent_memory",
    "save_agent_memory",
    "build_memory_prompt",
    # Messaging
    "DebateMessage",
    "Mailbox",
    "MessageRouter",
    "get_message_router",
    "reset_message_router",
    "send_to_agent",
    "broadcast",
    # Agent
    "DebaterConfig",
    "DebaterAgent",
    "create_debater_pair",
    # Loop
    "DebateState",
    "DebateModerator",
    "run_debate",
    "run_debate_stream",
]