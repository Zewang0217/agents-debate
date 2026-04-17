# Debate PRD Generator

辩论式 PRD 生成系统 - 通过两个 Agent 辩论生成产品需求文档。

## 功能特性

- **辩论式需求分析**: 两个 Agent 代表不同立场辩论，从多角度审视需求
- **智能中控协调**: Moderator Agent 引导流程、记录观点、检测共识
- **灵活的用户介入**: 支持 6 种触发用户仲裁的条件
- **自动化 PRD 生成**: 辩论结束后自动生成 Markdown 格式的 PRD
- **自定义 LLM 配置**: 支持任意兼容 OpenAI 格式的 API（DeepSeek、Ollama 等）

## 预设角色组合

1. **PM vs Dev**: 产品需求视角 vs 技术可行性视角
2. **Business vs Security**: 业务增长 vs 安全合规
3. **UX vs Architecture**: 用户体验 vs 系统架构

## 安装

```bash
cd /home/zewang/PROJECTS/agents-debate
pip install -e .
```

## LLM 配置

### 方式1: 环境变量（推荐）

```bash
# OpenAI
export OPENAI_API_KEY=your_openai_key

# DeepSeek
export OPENAI_API_KEY=your_deepseek_key
export OPENAI_BASE_URL=https://api.deepseek.com/v1
export OPENAI_MODEL=deepseek-chat

# Ollama (本地)
export OPENAI_API_KEY=ollama
export OPENAI_BASE_URL=http://localhost:11434/v1
export OPENAI_MODEL=llama3

# 其他兼容 OpenAI 的服务
export OPENAI_API_KEY=your_key
export OPENAI_BASE_URL=https://your-api.com/v1
export OPENAI_MODEL=your_model
```

### 方式2: 命令行参数

```bash
# 使用 DeepSeek
debate-prd --base-url https://api.deepseek.com/v1 --model deepseek-chat --api-key your_key

# 使用 Ollama
debate-prd --base-url http://localhost:11434/v1 --model llama3 --api-key ollama

# 指定议题和预设
debate-prd --topic "开发用户登录系统" --preset pm_vs_dev --max-rounds 8
```

### 方式3: 代码配置

```python
from debate_prd.config.settings import LLMConfig

llm_config = LLMConfig(
    api_key="your_key",
    base_url="https://api.deepseek.com/v1",
    model="deepseek-chat",
)
```

## 快速开始

```bash
# 交互模式
debate-prd

# 直接指定参数
debate-prd --topic "开发一个支付系统" --preset business_vs_security
```

## 用户介入触发条件

- 辩论超过 N 轮无共识
- 双方观点根本性冲突
- 需要业务决策（优先级、取舍）
- 用户输入 `仲裁` 关键词
- Agent 主动请求（`[REQUEST_ARBITRATION]` 标记）
- Moderator 自主判断需要用户介入

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--api-key` | API Key | 环境变量 OPENAI_API_KEY |
| `--base-url` | API Base URL | https://api.openai.com/v1 |
| `--model` | 模型名称 | gpt-4o-mini |
| `--preset` | 预设角色组合 | 交互选择 |
| `--topic` | 辩论议题 | 交互输入 |
| `--max-rounds` | 最大辩论轮数 | 10 |
| `--output-dir` | PRD 输出目录 | ./output |

## 项目结构

```
src/debate_prd/
├── agents/          # Agent 实现
│   ├── debater.py   # 辩论 Agent
│   └── moderator.py # 中控 Agent
├── team/            # 团队编排
│   └── debate_team.py
├── config/          # 配置和预设
│   ├── presets.py   # 角色预设
│   ├── settings.py  # LLM 和系统配置
│   └── prompts.py   # 系统提示词
├── output/          # PRD 生成
│   ├── prd_generator.py
│   └── recorder.py
└── cli/             # 命令行入口
```

## 示例

```bash
# 运行基础示例
python examples/basic_debate.py

# 自定义角色示例
python examples/custom_roles.py
```

## 支持的 LLM 服务

任何兼容 OpenAI API 格式的服务都可以使用：

- OpenAI (GPT-4, GPT-4o-mini, etc.)
- DeepSeek
- Claude (通过兼容接口)
- 本地模型 (Ollama, LM Studio, etc.)
- 其他云服务 (Azure OpenAI, etc.)