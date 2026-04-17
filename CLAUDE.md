# agents-debate 项目

## 项目概述
辩论式 PRD 生成系统：基于 Claude Code 多代理设计模式，两个 Debater Agent 通过消息互发实现真正的"吵架"式辩论，Moderator 协调流程并生成 PRD。

## 技术栈
- AsyncOpenAI - LLM 客户端（兼容 OpenAI/DeepSeek/Ollama）
- Textual (>=0.47) - TUI 界面
- Rich (>=13.0) - 终端渲染

## 运行命令
```bash
# 使用 uv 创建虚拟环境
uv venv && source .venv/bin/activate
uv pip install -e .

# 加载环境变量
source .env && export OPENAI_API_KEY OPENAI_BASE_URL OPENAI_MODEL

# 启动
debate-prd --tui --topic "议题名称"  # TUI 模式（推荐）
debate-prd --topic "议题名称"        # CLI 模式
```

## TUI 快捷键
| 键 | 功能 |
|---|------|
| `B` | 开始辩论 |
| `S` | 停止辩论 |
| `Q` | 退出 |

## LLM 配置
环境变量配置（兼容 OpenAI 格式）：
- `OPENAI_API_KEY` - API Key
- `OPENAI_BASE_URL` - API URL（默认 OpenAI，可设 DeepSeek/Ollama）
- `OPENAI_MODEL` - 模型名称

## 项目结构
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

## 记忆系统
Agent 记忆存储在 `.claude/agent-memory/`：
```
.claude/agent-memory/
├── debater1_PM/MEMORY.md    # PM Agent 记忆
├── debater2_Dev/MEMORY.md   # Dev Agent 记忆
```

## 预设角色
- `pm_vs_dev` - 产品 vs 技术
- `business_vs_security` - 业务 vs 安全
- `ux_vs_architecture` - 体验 vs 架构

## 注意事项
- `.env` 包含 API Key，已排除 git
- 输出目录 `./output/` 也已排除
- **TUI CSS 必须使用硬编码十六进制颜色**（如 `#c9d1d9`），禁止使用 CSS 变量或 f-string，否则 Textual 会报错或文字不可见