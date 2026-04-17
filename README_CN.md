# 辩论式 PRD 生成系统

English | [中文文档](./README_CN.md)

> **通过 AI Agent 辩论生成更全面的产品需求文档**

一个创新的 PRD 生成系统，两个持有不同观点的 AI Agent 就你的产品需求进行辩论，确保文档更全面、更深思熟虑。

![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)
![AutoGen](https://img.shields.io/badge/AutoGen-0.4+-green.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## 🎯 功能特性

- **🤖 AI 辩论系统**: 两个 Agent 从不同视角辩论（PM vs Dev、Business vs Security、UX vs Architecture）
- **🎯 智能中控**: 协调辩论流程、记录共识、检测何时需要人工介入
- **🎨 炫酷 TUI 界面**: 交互式终端界面，实时消息显示、统计、PRD 预览
- **⚙️ 灵活的 LLM 支持**: 兼容任意 OpenAI 格式 API（OpenAI、DeepSeek、Claude、Ollama 等）
- **📝 自动 PRD 生成**: Markdown 格式输出，包含辩论历史

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
# TUI 模式（推荐）- 炫酷交互界面
debate-prd-tui

# CLI 模式 - 传统命令行
debate-prd --topic "用户认证系统" --preset pm_vs_dev
```

## 🎭 预设角色组合

| 预设 | 辩论方 1 | 辩论方 2 | 关注点 |
|------|----------|----------|--------|
| `pm_vs_dev` | PM（产品价值） | Dev（技术可行性） | 产品 vs 实现 |
| `business_vs_security` | Business（业务增长） | Security（安全合规） | 速度 vs 安全 |
| `ux_vs_architecture` | UX（用户体验） | Arch（系统稳定） | 易用 vs 性能 |

## 🖥️ TUI 界面

启动 `debate-prd-tui` 体验交互式终端界面：

```
┌──────────────────────────────────────────────────────────────┐
│ 🎮 辩论式 PRD 生成系统                                        │
├─────────────┬──────────────────────────┬────────────────────┤
│ 🎯 角色预设  │  实时辩论消息             │ 📊 统计状态        │
│ [下拉选择]  │  [Moderator] 开始辩论...   │ 轮数: 3/10        │
│             │  [PM] 产品价值优先...      │ 共识: 2           │
│ 📝 辩论议题  │  [Dev] 技术成本考量...     │ 分歧: 1           │
│ [文本输入]  │  ...                      │                    │
│             │                           │ 📄 PRD 预览        │
│ ▶ 开始辩论   │                           │                    │
│ ⏸ 请求仲裁   │                           │                    │
│ ⏹ 停止      │                           │                    │
├─────────────┴──────────────────────────┴────────────────────┤
│ [S]开始 [A]仲裁 [Q]退出 [D]深色 [C]清空                        │
└──────────────────────────────────────────────────────────────┘
```

### TUI 快捷键

| 键 | 功能 |
|---|------|
| `S` | 开始辩论 |
| `A` | 请求仲裁 |
| `Q` | 退出 |
| `D` | 切换深色模式 |
| `C` | 清空辩论区 |

## ⚡ 用户介入触发条件

中控 Agent 在以下情况请求用户仲裁：

1. **轮数上限**: 辩论超过 N 轮未达成共识
2. **僵局检测**: 连续多轮无实质进展
3. **业务决策**: 需要确定优先级或取舍
4. **关键词触发**: 用户输入"仲裁"
5. **Agent 请求**: 任何 Agent 发送 `[REQUEST_ARBITRATION]`
6. **中控判断**: 中控自主决定需要用户介入

## 🛠️ 项目结构

```
agents-debate/
├── src/debate_prd/
│   ├── agents/           # Agent 实现
│   │   ├── debater.py    # 辩论 Agent
│   │   └── moderator.py  # 中控 Agent
│   ├── team/             # 团队编排
│   │   └── debate_team.py
│   ├── config/           # 配置
│   │   ├── presets.py    # 角色预设
│   │   ├── settings.py   # LLM 和系统配置
│   │   └── prompts.py    # 系统提示词
│   ├── output/           # 输出生成
│   │   ├── prd_generator.py
│   │   └── recorder.py
│   └── cli/              # CLI 入口
│       ├── main.py       # 传统 CLI
│       └── tui.py        # TUI 界面
├── examples/             # 示例脚本
├── tests/                # 单元测试
└── pyproject.toml        # 项目配置
```

## 🔧 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--api-key` | API Key | `$OPENAI_API_KEY` |
| `--base-url` | API Base URL | `https://api.openai.com/v1` |
| `--model` | 模型名称 | `gpt-4o-mini` |
| `--preset` | 角色预设 | 交互选择 |
| `--topic` | 辩论议题 | 交互输入 |
| `--max-rounds` | 最大辩论轮数 | 10 |
| `--output-dir` | PRD 输出目录 | `./output` |

## 🤝 贡献

欢迎贡献！请随时提交 Pull Request。

## 📄 许可证

本项目采用 MIT 许可证 - 详情见 [LICENSE](./LICENSE) 文件。

---

**由 zewang 用 ❤️ 制作**