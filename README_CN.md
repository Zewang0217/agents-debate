# 辩论式 PRD 生成系统

English | [中文文档](./README_CN.md)

> **通过 AI Agent 辩论生成更全面的产品需求文档**

一个创新的 PRD 生成系统，两个持有不同观点的 AI Agent 就你的产品需求进行辩论，确保文档更全面、更深思熟虑。

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🎯 功能特性

- **🤖 AI 辩论系统**: 两个 Agent 从不同视角辩论（PM vs Dev、Business vs Security、UX vs Architecture）
- **💬 消息传递架构**: Agent 通过消息互发实现真正的"吵架"式辩论
- **🧠 记忆系统**: 每个 Agent 有持久化记忆（project scope），从历史辩论中学习
- **🎨 炫酷 TUI 界面**: 深色主题 + 卡片式消息显示
- **⚙️ 灵活的 LLM 支持**: 兼容任意 OpenAI 格式 API（OpenAI、DeepSeek、Claude、Ollama 等）
- **📝 自动 PRD 生成**: Markdown 格式输出，包含辩论摘要

## 🚀 快速开始

### 安装（使用 uv）

```bash
git clone https://github.com/zewang/agents-debate.git
cd agents-debate

# 创建虚拟环境并安装依赖
uv venv && source .venv/bin/activate
uv pip install -e .
```

### 配置

创建 `.env` 文件或设置环境变量：

```bash
# OpenAI
export OPENAI_API_KEY=your_openai_key

# DeepSeek
export OPENAI_API_KEY=your_deepseek_key
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export OPENAI_MODEL=deepseek-chat

# Ollama（本地模型）
export OPENAI_API_KEY=ollama
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_MODEL=llama3
```

### 运行

```bash
# TUI 模式（推荐）- 交互式界面
debate-prd --tui --topic "用户认证系统"

# CLI 模式 - 传统命令行
debate-prd --topic "用户认证系统" --preset pm_vs_dev
```

### TUI 快捷键

| 键 | 功能 |
|---|------|
| `B` | 开始辩论 |
| `S` | 停止辩论 |
| `Q` | 退出 |

## 🎭 预设角色组合

| 预设 | 辩论方 1 | 辩论方 2 | 关注点 |
|------|----------|----------|--------|
| `pm_vs_dev` | PM（产品价值） | Dev（技术可行性） | 产品 vs 实现 |
| `business_vs_security` | Business（业务增长） | Security（安全合规） | 速度 vs 安全 |
| `ux_vs_architecture` | UX（用户体验） | Arch（系统稳定） | 易用 vs 性能 |

## 🖥️ TUI 界面

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

## 🛠️ 架构设计

基于 Claude Code 的 Agent 设计模式：

```
src/debate_prd/
├── core/                 # 核心辩论系统
│   ├── messaging/        # 消息传递（mailbox）
│   ├── memory/           # Agent 记忆（project scope）
│   ├── spawn/            # Debater Agent 创建
│   └── debate_loop.py    # 辩论循环控制
├── config/               # 配置
│   ├── presets.py        # 角色预设
│   └── settings.py       # LLM 和系统配置
├── output/               # 输出生成
│   └ prd_generator.py   # PRD 生成器
└── cli/                  # CLI 入口
    ├── main.py           # 传统 CLI
    └── tui.py            # TUI 界面
```

## 📁 记忆系统

Agent 记忆存储在 `.claude/agent-memory/`：

```
.claude/agent-memory/
├── debater1_PM/MEMORY.md    # PM Agent 记忆
├── debater2_Dev/MEMORY.md   # Dev Agent 记忆
```

## 🔧 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--tui` | 启动 TUI 模式 | False |
| `--api-key` | API Key | `$OPENAI_API_KEY` |
| `--base-url` | API Base URL | `https://api.openai.com/v1` |
| `--model` | 模型名称 | `gpt-4o-mini` |
| `--preset` | 角色预设 | `pm_vs_dev` |
| `--topic` | 辩论议题 | 交互输入 |
| `--max-rounds` | 最大辩论轮数 | `10` |
| `--output-dir` | PRD 输出目录 | `./output` |

## 🤝 贡献

欢迎贡献！请随时提交 Pull Request。

## 📄 许可证

本项目采用 MIT 许可证 - 详情见 [LICENSE](./LICENSE) 文件。

---

**由 zewang 用 ❤️ 制作**