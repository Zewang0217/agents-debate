# agents-debate 项目

## 项目概述
辩论式 PRD 生成系统：两个 Agent 代表不同立场辩论，Moderator 协调并生成 PRD。

## 技术栈
- AutoGen (autogen-agentchat>=0.4) - 多 Agent 框架
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
debate-prd-tui  # TUI 模式（推荐）
debate-prd      # CLI 模式
```

## LLM 配置
环境变量配置（兼容 OpenAI 格式）：
- `OPENAI_API_KEY` - API Key
- `OPENAI_BASE_URL` - API URL（默认 OpenAI，可设 DeepSeek/Ollama）
- `OPENAI_MODEL` - 模型名称

## 项目结构
```
src/debate_prd/
├── agents/     - DebaterAgent, ModeratorAgent
├── team/       - DebateTeam (SelectorGroupChat)
├── config/     - presets (角色预设), settings (LLM配置)
├── output/     - PRDGenerator, DebateRecorder
├── cli/        - main.py (CLI), tui.py (TUI)
```

## 预设角色
- `pm_vs_dev` - 产品 vs 技术
- `business_vs_security` - 业务 vs 安全
- `ux_vs_architecture` - 体验 vs 架构

## 注意事项
- `.env` 包含 API Key，已排除 git
- 输出目录 `./output/` 也已排除
- 用户介入标记：`[REQUEST_ARBITRATION]`、`[AGREE]`、`仲裁`