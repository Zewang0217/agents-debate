# Debate PRD Generator

[中文文档](./README_CN.md) | English

> **Generate comprehensive Product Requirement Documents through AI agent debates**

An innovative PRD generation system where two AI agents with different perspectives debate your product requirements, ensuring more thorough and well-considered documentation.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🎯 Features

- **🤖 AI Debate System**: Two agents debate from different perspectives (PM vs Dev, Business vs Security, UX vs Architecture)
- **💬 Message-based Architecture**: Agents communicate through message passing, enabling true "argument" style debates
- **🧠 Memory System**: Each agent has persistent memory (project scope), learning from past debates
- **🎨 Cool TUI Interface**: Dark theme with card-style message display
- **⚙️ Flexible LLM Support**: Compatible with any OpenAI-format API (OpenAI, DeepSeek, Claude, Ollama, etc.)
- **📝 Auto PRD Generation**: Markdown-formatted PRD output with debate summary

## 🚀 Quick Start

### Installation (with uv)

```bash
git clone https://github.com/zewang/agents-debate.git
cd agents-debate

# Create virtual environment and install dependencies
uv venv && source .venv/bin/activate
uv pip install -e .
```

### Configuration

Create a `.env` file or set environment variables:

```bash
# For OpenAI
export OPENAI_API_KEY=your_openai_key

# For DeepSeek
export OPENAI_API_KEY=your_deepseek_key
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export OPENAI_MODEL=deepseek-chat

# For Ollama (local)
export OPENAI_API_KEY=ollama
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_MODEL=llama3
```

### Run

```bash
# TUI Mode (Recommended) - Interactive interface
debate-prd --tui --topic "User authentication system"

# CLI Mode - Traditional command line
debate-prd --topic "User authentication system" --preset pm_vs_dev
```

### TUI Controls

| Key | Action |
|-----|--------|
| `B` | Start debate |
| `S` | Stop debate |
| `Q` | Quit |

## 🎭 Preset Role Combinations

| Preset | Debater 1 | Debater 2 | Focus |
|--------|-----------|-----------|-------|
| `pm_vs_dev` | PM (Product Value) | Dev (Technical Feasibility) | Product vs Implementation |
| `business_vs_security` | Business (Growth) | Security (Compliance) | Speed vs Safety |
| `ux_vs_architecture` | UX (User Experience) | Arch (System Stability) | Usability vs Performance |

## 🖥️ TUI Interface

```
┌──────────────────────────────────────────────────────────────┐
│ 辩论式 PRD 生成                                               │
├─────────────┬──────────────────────────┬────────────────────┤
│ 状态        │  消息卡片                 │ PRD 预览           │
│ 待开始      │  【PM】产品价值优先...     │                    │
│ 议题        │  【Dev】技术成本考量...    │ # PRD: ...         │
│ 轮数        │  ...                      │                    │
│ 预设        │                           │                    │
├─────────────┴──────────────────────────┴────────────────────┤
│ [B]开始 [S]停止 [Q]退出                                       │
└──────────────────────────────────────────────────────────────┘
```

## 🛠️ Architecture

Based on Claude Code's agent design patterns:

```
src/debate_prd/
├── core/                 # Core debate system
│   ├── messaging/        # Message passing (mailbox)
│   ├── memory/           # Agent memory (project scope)
│   ├── spawn/            # Debater agent creation
│   └── debate_loop.py    # Debate loop control
├── config/               # Configuration
│   ├── presets.py        # Role presets
│   └── settings.py       # LLM & system settings
├── output/               # Output generation
│   └── prd_generator.py  # PRD generator
└── cli/                  # CLI entry points
    ├── main.py           # Traditional CLI
    └── tui.py            # TUI interface
```

## 📁 Memory System

Agents store memories in `.claude/agent-memory/`:

```
.claude/agent-memory/
├── debater1_PM/MEMORY.md    # PM agent memory
├── debater2_Dev/MEMORY.md   # Dev agent memory
```

## 🔧 CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--tui` | Launch TUI mode | False |
| `--api-key` | API Key | `$OPENAI_API_KEY` |
| `--base-url` | API Base URL | `https://api.openai.com/v1` |
| `--model` | Model name | `gpt-4o-mini` |
| `--preset` | Role preset | `pm_vs_dev` |
| `--topic` | Debate topic | Interactive input |
| `--max-rounds` | Max debate rounds | `10` |
| `--output-dir` | PRD output directory | `./output` |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

---

**Made with ❤️ by zewang**