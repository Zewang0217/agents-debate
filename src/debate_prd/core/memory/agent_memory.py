"""Agent记忆系统 - 基于Claude Code设计模式

支持三种scope:
- user: ~/.claude/agent-memory/ (全局)
- project: .claude/agent-memory/ (项目级)
- local: .claude/agent-memory-local/ (本地)

默认使用project scope
"""

from pathlib import Path
from typing import Literal
import os


MemoryScope = Literal["user", "project", "local"]


def get_memory_base_dir() -> Path:
    """获取记忆系统基础目录"""
    # 用户级记忆目录
    config_home = os.environ.get("CLAUDE_CONFIG_HOME", Path.home() / ".claude")
    return Path(config_home)


def get_agent_memory_dir(agent_type: str, scope: MemoryScope = "project") -> Path:
    """获取Agent记忆目录

    Args:
        agent_type: Agent类型名（如 'debater1_pm', 'debater2_dev'）
        scope: 记忆scope

    Returns:
        记忆目录路径
    """
    # 清理agent_type（替换冒号）
    safe_name = agent_type.replace(":", "-")

    cwd = Path.cwd()

    if scope == "user":
        return get_memory_base_dir() / "agent-memory" / safe_name
    elif scope == "project":
        return cwd / ".claude" / "agent-memory" / safe_name
    elif scope == "local":
        return cwd / ".claude" / "agent-memory-local" / safe_name
    else:
        return cwd / ".claude" / "agent-memory" / safe_name


def get_memory_entrypoint(agent_type: str, scope: MemoryScope = "project") -> Path:
    """获取记忆文件入口点 (MEMORY.md)"""
    return get_agent_memory_dir(agent_type, scope) / "MEMORY.md"


def ensure_memory_dir_exists(memory_dir: Path) -> None:
    """确保记忆目录存在"""
    memory_dir.mkdir(parents=True, exist_ok=True)


def load_agent_memory(agent_type: str, scope: MemoryScope = "project") -> str:
    """加载Agent记忆内容

    Args:
        agent_type: Agent类型名
        scope: 记忆scope

    Returns:
        记忆内容字符串，如果不存在则返回空字符串
    """
    memory_file = get_memory_entrypoint(agent_type, scope)

    if not memory_file.exists():
        return ""

    return memory_file.read_text(encoding="utf-8")


def save_agent_memory(
    agent_type: str,
    content: str,
    scope: MemoryScope = "project"
) -> Path:
    """保存Agent记忆

    Args:
        agent_type: Agent类型名
        content: 记忆内容
        scope: 记忆scope

    Returns:
        保存的文件路径
    """
    memory_dir = get_agent_memory_dir(agent_type, scope)
    ensure_memory_dir_exists(memory_dir)

    memory_file = get_memory_entrypoint(agent_type, scope)
    memory_file.write_text(content, encoding="utf-8")

    return memory_file


def build_memory_prompt(
    agent_type: str,
    scope: MemoryScope = "project",
    extra_guidelines: list[str] = None
) -> str:
    """构建记忆提示词

    Args:
        agent_type: Agent类型名
        scope: 记忆scope
        extra_guidelines: 额外的指导原则

    Returns:
        记忆提示词
    """
    memory_dir = get_agent_memory_dir(agent_type, scope)
    memory_file = get_memory_entrypoint(agent_type, scope)

    # Scope说明
    scope_notes = {
        "user": "- Since this memory is user-scope, keep learnings general since they apply across all projects",
        "project": "- Since this memory is project-scope, tailor your memories to this specific debate project",
        "local": "- Since this memory is local-scope (not checked into version control), it's private to this machine",
    }

    guidelines = [scope_notes.get(scope, scope_notes["project"])]
    if extra_guidelines:
        guidelines.extend(extra_guidelines)

    guidelines_text = "\n".join(guidelines)

    return f"""
# Persistent Agent Memory

Memory directory: {memory_dir}
Memory file: {memory_file}

## Usage
- Read existing memories from {memory_file} at the start of each debate
- Write new learnings to {memory_file} at the end of each debate
- Use this memory to improve your debate performance over time

## Guidelines
{guidelines_text}

## Memory Format
```markdown
# Agent Memory: {agent_type}

## My Stance
[Your core position and principles]

## Arguments I've Used
[Successful arguments that worked]

## Opponent's Attacks
[Points raised by opponent → My responses]

## Consensus Reached
[Points where we agreed]

## Learnings
[What I learned from this debate]
```

Load existing memory and incorporate it into your debate strategy.
"""


def get_memory_scope_display(scope: MemoryScope | None) -> str:
    """获取scope显示文本"""
    if scope == "user":
        base = get_memory_base_dir()
        return f"User ({base / 'agent-memory'})"
    elif scope == "project":
        return "Project (.claude/agent-memory)"
    elif scope == "local":
        return "Local (.claude/agent-memory-local)"
    else:
        return "None"