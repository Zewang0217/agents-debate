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
- **🎯 加权共识检测**: 自动检测共识或僵局，加权评分（AGREE=1.0, PARTIAL_AGREE=0.5, DISAGREE=1.0）
- **👤 用户干预**: Moderator 在关键决策点或僵局时询问用户
- **📝 自动 PRD 生成**: Markdown 格式输出，包含分类条目和共识分析
- **⚙️ 灵活的 LLM 支持**: 兼容任意 OpenAI 格式 API（OpenAI、DeepSeek、Claude、Ollama 等）

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
# 交互模式（推荐）- 先选预设，再输入议题
debate-prd

# 快速启动 - 指定预设和议题
debate-prd --preset 1 --topic "用户认证系统"

# 查看系统简介
debate-prd --info

# 列出预设角色
debate-prd --list-presets
```

## 📋 工作流程

1. **澄清阶段** - Moderator 通过问答收集需求细节
2. **PRD 基础版生成** - 从收集信息生成初始 PRD 概要
3. **辩论阶段** - Agent 自由发表观点并反驳
4. **共识检测** - 加权评分自动检测共识达成或僵局
5. **用户干预** - 关键决策点或僵局时询问用户
6. **PRD 生成** - 综合辩论结果生成最终文档

## 🎭 预设角色组合

| 编号 | 预设 | 辩论方 1 | 辩论方 2 | 关注点 |
|------|------|----------|----------|--------|
| 1 | `pm_vs_dev` | PM（产品价值） | Dev（技术可行性） | 产品 vs 实现 |
| 2 | `business_vs_security` | Business（业务增长） | Security（安全合规） | 速度 vs 安全 |
| 3 | `ux_vs_architecture` | UX（用户体验） | Arch（系统稳定） | 易用 vs 性能 |

## 🏷️ 输出标记

Agent 使用特殊标记表达观点：

| 标记 | 含义 |
|------|------|
| `[AGREE:内容]` | 完全认同 |
| `[PARTIAL_AGREE:内容+建议]` | 有保留的认同 |
| `[DISAGREE:内容+理由]` | 明确分歧（质疑时必须使用） |
| `[PRD_ITEM] 功能描述` | PRD 条目建议 |

## 🔧 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--preset` | 预设编号(1-3)或名称 | 交互选择 |
| `--topic` | 辩论议题 | 交互输入 |
| `--max-rounds` | 最大辩论轮数 | `6` |
| `--output-dir` | PRD 输出目录 | `./output` |
| `--info` | 显示系统简介 | - |
| `--list-presets` | 列出预设角色 | - |

## 🛠️ 架构设计

基于 Claude Code 的 Agent 设计模式：

```
src/debate_prd/
├── core/                 # 核心辩论系统
│   ├── messaging/        # 消息传递（mailbox）
│   ├── memory/           # Agent 记忆（project scope）
│   ├── spawn/            # Debater Agent 创建
│   ├── tools/            # Moderator 干预工具
│   └── debate_loop.py    # 辩论循环控制
├── config/               # 配置
│   ├── presets.py        # 角色预设
│   ├── prompts.py        # Agent 提示词
│   └── settings.py       # LLM 和系统配置
├── output/               # 输出生成
│   └── prd_generator.py  # PRD 生成器
└── cli/                  # CLI 入口
    ├── main.py           # 统一 CLI
    ├── theme.py          # Rosé Pine 颜色主题
    └── formatting.py     # Rich 输出工具
```

## 📁 记忆系统

Agent 记忆存储在 `.claude/agent-memory/`：

```
.claude/agent-memory/
├── debater1_PM/MEMORY.md    # PM Agent 记忆
├── debater2_Dev/MEMORY.md   # Dev Agent 记忆
```

## 🤝 贡献

欢迎贡献！请随时提交 Pull Request。

## 📄 许可证

本项目采用 MIT 许可证 - 详情见 [LICENSE](./LICENSE) 文件。

---

**由 zewang 用 ❤️ 制作**