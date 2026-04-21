# Debate PRD Generator

[中文文档](./README_CN.md) | English

> **Generate comprehensive Product Requirement Documents through AI agent debates**

An innovative PRD generation system where two AI agents with different perspectives debate your product requirements, ensuring more thorough and well-considered documentation.

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🎯 Features

- **🤖 AI Debate System**: Two agents debate from different perspectives (PM vs Dev, Business vs Security, UX vs Architecture)
- **💬 Message-based Architecture**: Agents communicate through message passing, enabling true "argument" style debates
- **🧠 Memory System**: Each agent has isolated memory per debate session (local scope), preventing cross-topic pollution
- **🎯 Weighted Consensus Detection**: Automatically detects consensus or stalemate with weighted scoring (AGREE=1.0, PARTIAL_AGREE=0.5, DISAGREE=1.0)
- **👤 User Intervention**: Moderator asks for user input on critical decisions or stalemates
- **📝 Auto PRD Generation**: Markdown-formatted PRD output with categorized items and consensus analysis
- **⚙️ Flexible LLM Support**: Compatible with any OpenAI-format API (OpenAI, DeepSeek, Claude, Ollama, etc.)

**👉 [See Full Example](./examples/aichat-sandbox-demo.md)** - A complete debate session generating PRD for "AIChat Sandbox Mode"

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

# Run after loading environment
source .env && export OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL
```

### Run

```bash
# Load environment variables first
source .env && export OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL

# Interactive Mode (Recommended) - Select preset, then enter topic
debate-prd

# Quick Start - Specify preset and topic
debate-prd --preset 1 --topic "User authentication system"

# View system info
debate-prd --info

# List preset roles
debate-prd --list-presets
```

## 📋 Workflow

1. **Clarification Phase** - Moderator collects requirement details through Q&A
2. **PRD Base Generation** - Generate initial PRD summary from collected info
3. **Debate Phase** - Agents freely express views and rebut each other
4. **Consensus Detection** - Weighted scoring detects consensus or stalemate
5. **User Intervention** - Moderator asks user on critical decisions or stalemates
6. **PRD Generation** - Synthesize debate results into final document

## 🎭 Preset Role Combinations

| # | Preset | Debater 1 | Debater 2 | Focus |
|---|--------|-----------|-----------|-------|
| 1 | `pm_vs_dev` | PM (Product Value) | Dev (Technical Feasibility) | Product vs Implementation |
| 2 | `business_vs_security` | Business (Growth) | Security (Compliance) | Speed vs Safety |
| 3 | `ux_vs_architecture` | UX (User Experience) | Arch (System Stability) | Usability vs Performance |

## 🏷️ Output Markers

Agents use special markers to express opinions:

| Marker | Meaning |
|--------|---------|
| `[AGREE:content]` | Full agreement |
| `[PARTIAL_AGREE:content+suggestion]` | Partial agreement with reservation |
| `[DISAGREE:content+reason]` | Clear disagreement (required for challenges) |
| `[PRD_ITEM] feature description` | PRD feature suggestion |

## 🔧 CLI Options

| Option | Description | Default |
|--------|-------------|---------|
| `--preset` | Preset number (1-3) or name | Interactive selection |
| `--topic` | Debate topic | Interactive input |
| `--max-rounds` | Max debate rounds | `6` |
| `--output-dir` | PRD output directory | `./output` |
| `--info` | Show system info | - |
| `--list-presets` | List preset roles | - |

## 🛠️ Architecture

```
src/debate_prd/
├── core/                 # Core debate system
│   ├── messaging/        # Message passing (mailbox)
│   ├── memory/           # Agent memory (project scope)
│   ├── spawn/            # Debater agent creation
│   ├── tools/            # Moderator intervention tools
│   └── debate_loop.py    # Debate loop control
├── config/               # Configuration
│   ├── presets.py        # Role presets
│   ├── prompts.py        # Agent prompts
│   └── settings.py       # LLM & system settings
├── output/               # Output generation
│   └── prd_generator.py  # PRD generator
└── cli/                  # CLI entry
    ├── main.py           # Unified CLI
    ├── theme.py          # Rosé Pine color theme
    └── formatting.py     # Rich output helpers
```

## 📁 Memory System

Agents use **local scope** memory by default - each debate session starts fresh, preventing cross-topic pollution. Memory is stored in `.claude/agent-memory/`:

```
.claude/agent-memory/
├── debater1_PM/MEMORY.md    # PM agent memory (session-based)
├── debater2_Dev/MEMORY.md   # Dev agent memory (session-based)
```

**Note:** Previous `project scope` memory caused hallucination issues where agents referenced unrelated topics from past debates. Now each topic gets clean, isolated context.

**Anti-Hallucination Features:**
- Topic constraint enforcement in every agent response
- Hallucination detection for off-topic references
- Consensus validation against original topic

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](./LICENSE) file for details.

---

**Made with ❤️ by zewang**