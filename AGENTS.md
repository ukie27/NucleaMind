# NucleaMind 项目指南（AGENTS.md）

本文件为本仓库中的 AI 编码代理提供开发指引。

## 项目概述

NucleaMind 是基于 [HKUDS/nanobot](https://github.com/HKUDS/nanobot)（MIT 协议）
独立开发的个人 AI Agent 项目，仓库与上游 Git 历史及协作流程均已分离。

- **当前状态**：代码库仍保留 nanobot 的完整结构（Agent Runtime、Channels、Tools、Memory、WebUI 等），可正常运行。
- **长期目标**：不是继续堆功能，而是把 nanobot 改造成**轻量、模块化、可扩展的 Agent Kernel**——核心保持最小化（只保留 Agent 执行循环、LLM 抽象层、消息系统、Session 管理、Context 构建接口、Tool 注册机制、Plugin Runtime、基础配置），具体能力（Telegram/Discord/Memory/Browser/MCP/WebUI/Automation/Multi-Agent 等）逐步抽离为可选插件。
- 愿景与开发原则详见 [`开发背景.md`](./开发背景.md)。

> **注意**：包名与导入路径目前仍是 `nanobot`（`pyproject.toml` 中 name 为 `nanobot-ai`），尚未做全局重命名。后续改造时再统一规划，不要在代码中混用 `nucleamind` 前缀。

## 开发命令

```bash
# Python：单测 / lint
.venv\Scripts\python.exe -m pytest tests/test_openai_api.py::test_function -v
.venv\Scripts\python.exe -m ruff check nanobot/

# 严格类型检查（与 CI 一致）
uv sync --all-extras --dev
uv run --no-sync python -m scripts.install_channel_dependencies --all-channels
uv run --no-sync basedpyright

# WebUI：dev server（代理 API/WS 到 gateway :8765）/ build / test
# 构建产物输出到 ../nanobot/web/dist（打进 Python wheel）
cd webui && bun run dev      # 或 NANOBOT_API_URL=... bun run dev
cd webui && bun run build
cd webui && bun run test

# Gateway
nanobot gateway
```

## Python 环境与沙箱

- 项目本地开发和测试统一使用仓库中的 `.venv`，所有 Python 命令均通过
  `.venv\Scripts\python.exe` 执行，例如
  `.venv\Scripts\python.exe -m pytest` 和
  `.venv\Scripts\python.exe -m pip install -e ".[dev]"`。
- 不要使用裸 `pip`、`pytest` 或系统 `python` 代替项目虚拟环境；只有在明确确认
  `.venv` 不存在时，才可以使用系统 Python 创建或修复虚拟环境。
- Python 虚拟环境与执行沙箱是两套独立机制：`.venv` 负责固定 Python 解释器和依赖，
  沙箱负责限制进程可访问的文件、目录和网络。沙箱不会提供或替代 Python 环境。
- 如果 `.venv` 在普通终端可用，但 Agent 执行时出现基础解释器不存在、访问被拒绝、
  依赖下载失败等问题，应先检查沙箱的文件或网络权限。不要仅凭沙箱内的失败判断
  `.venv` 已损坏，也不要因此绕过 `.venv` 改用系统 Python。
- 测试或开发命令确实需要访问工作区之外的基础解释器、缓存目录或网络时，应申请
  对应的沙箱权限，并在获得授权后继续使用 `.venv\Scripts\python.exe`。

## 高层架构（当前状态，源自 nanobot）

### 核心数据流

消息通过异步 `MessageBus`（`nanobot/bus/queue.py`）解耦聊天渠道与 agent 核心：

1. **Channels**（`nanobot/channels/`）接收外部平台消息，向总线发布 `InboundMessage` 事件。
2. **`AgentLoop`**（`nanobot/agent/loop.py`）消费入站消息，构建上下文，协调整个 turn。
3. **`AgentRunner`**（`nanobot/agent/runner.py`）执行真正的 LLM 对话循环：发送消息、接收 tool calls、执行工具、流式返回。
4. 响应以 `OutboundMessage` 事件发布回对应渠道。

### 关键子系统

- **Agent Loop**（`nanobot/agent/loop.py`、`runner.py`）：核心处理引擎。`AgentLoop` 管理 session keys、hooks、上下文构建；`AgentRunner` 执行带工具调用的多轮 LLM 对话。
- **LLM Providers**（`nanobot/providers/`）：Anthropic、OpenAI 兼容、OpenAI Responses API、Azure、Bedrock、GitHub Copilot、Codex 等，基于公共基类（`base.py`），含图像生成（`image_generation.py`）与音频转录（`transcription.py`）。`factory.py` / `registry.py` 负责实例化与模型发现。
- **Channels**（`nanobot/channels/`）：Telegram、Discord、Slack、Feishu、Matrix、WhatsApp、QQ、WeChat、WeCom、DingTalk、Email、MoChat、MS Teams、WebSocket、Mattermost。`manager.py` 通过 `pkgutil` 扫描自动发现，每个 channel 是自包含包。
- **Tools**（`nanobot/agent/tools/`）：文件系统、shell（含沙箱后端）、web 搜索/抓取、MCP servers、cron、notebook、subagent、长任务/持续目标（`long_task.py`）、图像生成、自修改。`pkgutil` 扫描 + entry-point 插件自动发现。
- **Memory**（`nanobot/agent/memory.py`）：会话历史持久化 + Dream 两阶段记忆整合，原子写（temp + fsync + rename）保证持久性。
- **Session Management**（`nanobot/session/`）：会话历史、上下文压缩、TTL 自动压缩（`manager.py`）、持续目标状态（`goal_state.py`）。
- **Config**（`nanobot/config/schema.py`、`loader.py`）：Pydantic 配置，从 `~/.nanobot/config.json` 加载，支持 camelCase 别名。
- **WebUI**（`webui/`）：Vite + React SPA，通过 WebSocket 多路复用协议与 gateway 通信。
- **API Server**（`nanobot/api/server.py`）：OpenAI 兼容 HTTP API（`/v1/chat/completions`、`/v1/models`）。
- **Command Router**（`nanobot/command/`）：斜杠命令路由与内置命令处理。
- **Skills**（`nanobot/skills/`）：内置技能定义（cron、github、image-generation 等），markdown + YAML frontmatter。
- **Security**（`nanobot/security/`）：PTH 文件守卫等安全措施，CLI 入口激活。

### 入口点

- **CLI**：`nanobot/cli/commands.py`
- **Python SDK**：`nanobot/nanobot.py`

## 架构约束与改造方向

改造时遵循以下边界（详见 [.agent/design.md](.agent/design.md)）：

1. **核心保持小，能力在边缘扩展**：新能力优先放到 `channels/`、`agent/tools/`、skills、MCP server 或未来的插件包中。`agent/loop.py` 与 `agent/runner.py` 是核心路径，改动必须克制且有明确理由。
2. **接口优先于实现**：不绑定具体数据库、聊天平台、模型供应商、工作流框架，优先设计抽象接口（Memory Interface、Context Interface、Message Interface、Agent Provider Interface）。
3. **机制优先于功能**：核心提供 Extension Mechanism、Lifecycle、Registry、Interface，而不是堆积具体功能。
4. **少结构、多智能**：优先简单可读的代码，不要引入不必要的框架层和间接层。
5. **优先重复而非过早抽象**：channel/provider 之间允许重复逻辑（发送重试、媒体处理、消息拆分），不要为消除重复引入复杂基类。
6. **在边界类型化动态数据**：wire payload、持久化记录、第三方 SDK 对象在拥有它们的边缘做解析/规范化，用 `TypedDict` 固定形状，不用 `Any` 向核心泄漏；`typing.cast` 必须有运行时检查支撑。
7. **显式优于魔法**：配置必须在 `config/schema.py` 中显式声明；错误处理抛清晰异常，不静默修正坏输入。

## 常见坑与安全边界

- 常见坑（`${VAR}` 语义、Windows 兼容、prompt 模板、上下文污染、原子写等）：[.agent/gotchas.md](.agent/gotchas.md)
- 安全边界（工作区路径解析、SSRF 防护、shell 沙箱，不可绕过）：[.agent/security.md](.agent/security.md)

## 参考项目读取规范

`references/` 是本地只读参考源码目录，默认被 Git 忽略。当前约定的参考项目及其导航文档位于 [`docs/references/`](./docs/references/README.md)。

- 不要全量读取 `references/`，先阅读 `docs/references/README.md` 和对应项目导航文档。
- 先按主题定位候选目录、文件和符号，再使用 `rg` 或索引查询缩小范围。
- 只有在需要确认具体实现、调用关系、生命周期或兼容性契约时，才读取相关源码和测试。
- `references/nanobot` 用于确认原始 nanobot 行为；`references/openclaw` 用于插件、SDK 和生态兼容研究；`references/pi` 用于极简 Agent、扩展点和运行时设计研究。
- 参考项目中的 `AGENTS.md` 只约束对该参考项目源码的阅读和解释，不覆盖 NucleaMind 的开发规则。
- 参考源码不是 NucleaMind 的实现目录。借鉴设计时，必须记录采用的边界和不采用的部分，避免直接复制与当前目标冲突的功能。
- 索引由 `scripts/reference_index.py` 生成，属于导航辅助数据，不是架构事实的唯一来源；索引过期时先重新生成。

## 项目文档规范

[`docs/project/README.md`](./docs/project/README.md) 是项目当前状态和开发进度的交接文档。
每次新会话开始较大开发任务前应先阅读；完成一个大模块、项目阶段或架构调整后必须更新。

- `开发背景.md` 只维护相对稳定的项目愿景、目标和原则，不记录阶段性进度。
- `docs/project/` 保持扁平，不按方案、计划、决策等类型继续拆分子目录。
- 开发模块时，可在 `docs/project/` 直接创建临时 Markdown 文档，记录目标、技术方案、
  任务拆分、风险和验收方式；文件名优先使用小写英文和短横线。
- 模块完成后，先把当前状态、关键结果和下一步工作更新到 `docs/project/README.md`，
  再将仍然有效的架构或使用说明更新到正式文档，最后删除对应临时开发文档。
- 参考项目导航资料放在 [`docs/references/`](./docs/references/README.md)，不要写入被
  Git 忽略的 `references/`。

## 指令文件边界

- 根目录 `AGENTS.md` 是本仓库 AI 编码代理的开发指引，`CLAUDE.md` 仅引用本文件。
- `nanobot/templates/AGENTS.md` 是运行时复制到用户 workspace 的 Agent 行为模板，不是仓库开发规范。
- 修改 `nanobot/templates/`、`nanobot/skills/` 中的说明会改变最终用户 Agent 的行为；不要把仓库开发流程、上游协作方式或当前重构任务写入这些运行时模板。

## 代码风格

- Python 3.11+，全 asyncio。
- 行宽 100。
- Lint：`ruff`（规则 E, F, I, N, W，忽略 E501）。
- 测试：pytest，`asyncio_mode = "auto"`。
- **不要运行 `ruff format`**（会对历史代码生成大面积无关 diff），只用 `ruff check`。

## 开发流程（本项目自主）

- 本项目独立开发，不向上游 nanobot 提交代码。
- 提交保持小且单一意图，便于回溯（commit message 用简洁中文或英文均可）。
- 仓库已重新 init，与上游 git 历史完全脱离；是否持续跟踪上游修复由项目自行决定。
