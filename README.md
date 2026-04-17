# Debate PRD Generator

[中文文档](./README_CN.md) | English

> **Generate comprehensive Product Requirement Documents through AI agent debates**

An innovative PRD generation system where two AI agents with different perspectives debate your product requirements, ensuring more thorough and well-considered documentation.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![AutoGen](https://img.shields.io/badge/AutoGen-0.4+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🎯 Features

- **🤖 AI Debate System**: Two agents debate from different perspectives (PM vs Dev, Business vs Security, UX vs Architecture)
- **🎯 Smart Moderator**: Orchestrates debates, records consensus, detects when human intervention is needed
- **🎨 Cool TUI Interface**: Interactive terminal UI with real-time message display, statistics, and PRD preview
- **⚙️ Flexible LLM Support**: Compatible with any OpenAI-format API (OpenAI, DeepSeek, Claude, Ollama, etc.)
- **📝 Auto PRD Generation**: Markdown-formatted PRD output with debate history

## 🚀 Quick Start

### Installation

```bash
git clone https://github.com/zewang/agents-debate.git
cd agents-debate
pip install -e .
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
# TUI Mode (Recommended) - Cool interactive interface
debate-prd-tui

# CLI Mode - Traditional command line
debate-prd --topic "User authentication system" --preset pm_vs_dev
```

## 📖 Documentation

- [中文文档](./README_CN.md)
- [Usage Guide](#usage)
- [TUI Interface](#tui-interface)
- [Presets](#presets)

## 🎭 Preset Role Combinations

| Preset | Debater 1 | Debater 2 | Focus |
|--------|-----------|-----------|-------|
| `pm_vs_dev` | PM (Product Value) | Dev (Technical Feasibility) | Product vs Implementation |
| `business_vs_security` | Business (Growth) | Security (Compliance) | Speed vs Safety |
| `ux_vs_architecture` | UX (User Experience) | Arch (System Stability) | Usability vs Performance |

## 🖥️ TUI Interface

Launch `debate-prd-tui` for an interactive terminal experience:

```
┌──────────────────────────────────────────────────────────────┐
│ 🎮 Debate PRD Generator                                       │
├─────────────┬──────────────────────────┬────────────────────┤
│ 🎯 Preset   │  Real-time Debate        │ 📊 Statistics      │
│ [Select]    │  [Moderator] Starting... │ Rounds: 3/10       │
│             │  [PM] Product value...   │ Consensus: 2       │
│ 📝 Topic    │  [Dev] Technical cost... │ Disagreements: 1   │
│ [Input]     │  ...                     │                    │
│             │                          │ 📄 PRD Preview     │
│ ▶ Start     │                          │                    │
│ ⏸ Arbitrate │                          │                    │
│ ⏹ Stop      │                          │                    │
├─────────────┴──────────────────────────┴────────────────────┤
│ [S]Start [A]Arbitrate [Q]Quit [D]Dark [C]Clear               │
└──────────────────────────────────────────────────────────────┘
```

### TUI Shortcuts

| Key | Action |
|-----|--------|
| `S` | Start debate |
| `A` | Request arbitration |
| `Q` | Quit |
| `D` | Toggle dark mode |
| `C` | Clear chat |

## ⚡ Human Intervention Triggers

The moderator requests user arbitration when:

1. **Round limit**: Debate exceeds N rounds without consensus
2. **Stalemate**: No progress for consecutive rounds
3. **Business decision**: Priority or trade-off needed
4. **Keyword trigger**: User inputs "仲裁" (arbitrate)
5. **Agent request**: Any agent sends `[REQUEST_ARBITRATION]`
6. **Moderator judgment**: Moderator decides user input is needed

## 🛠️ Project Structure

```
agents-debate/
├── src/debate_prd/
│   ├── agents/           # Agent implementations
│   │   ├── debater.py    # Debate agents
│   │   └── moderator.py  # Moderator agent
│   ├── team/             # Team orchestration
│   │   └── debate_team.py
│   ├── config/           # Configuration
│   │   ├── presets.py    # Role presets
│   │   ├── settings.py   # LLM & system settings
│   │   └── prompts.py    # System prompts
│   ├── output/           # Output generation
│   │   ├── prd_generator.py
│   │   └── recorder.py
│   └── cli/              # CLI entry points
│       ├── main.py       # Traditional CLI
│       └── tui.py        # TUI interface
├── examples/             # Example scripts
├── tests/                # Unit tests
└── pyproject.toml        # Project config
```

## 🔧 CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--api-key` | API Key | `$OPENAI_API_KEY` |
| `--base-url` | API Base URL | `https://api.openai.com/v1` |
| `--model` | Model name | `gpt-4o-mini` |
| `--preset` | Role preset | Interactive select |
| `--topic` | Debate topic | Interactive input |
| `--max-rounds` | Max debate rounds | 10 |
| `--output-dir` | PRD output directory | `./output` |

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

---

**Made with ❤️ by zewang**