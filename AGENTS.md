# NucleaMind 项目指南（AGENTS.md）

本文件为本仓库中的 AI 编码代理提供开发指引。

## 项目概述

NucleaMind 是基于 [HKUDS/nanobot](https://github.com/HKUDS/nanobot)（MIT 协议）
独立开发的个人 AI Agent 项目，仓库与上游 Git 历史及协作流程均已分离。

- **当前状态**：`D00` 已把仓库搬到目标结构（`src/` 布局 + 新层空骨架 + `legacy/` 隔离区）。遗留实现全部位于 `src/nucleamind/legacy/`，通过 `nm legacy` 可正常运行；新 Kernel 各层仍是空骨架。
- **长期目标**：不是继续堆功能，而是把 nanobot 改造成**轻量、模块化、可扩展的 Agent Kernel**——核心保持最小化（只保留 Agent 执行循环、LLM 抽象层、消息系统、Session 管理、Context 构建接口、Tool 注册机制、Plugin Runtime、基础配置），具体能力（Telegram/Discord/Memory/Browser/MCP/WebUI/Automation/Multi-Agent 等）逐步抽离为可选插件。
- 愿景与开发原则详见 [`docs/project/开发背景.md`](./docs/project/开发背景.md)。

> **命名（`D00` 已落地，技术方案 §4.5）**：Python 包为 `nucleamind`，发行名 `nucleamind`，
> CLI 命令只有 `nm`（不保留 `nanobot` 别名）。新层只读 `NUCLEAMIND_*`、
> `~/.nucleamind/<instance>/` 和 snake_case 配置，**不双读旧格式、不写长期兼容垫片**。
> `src/nucleamind/legacy/` 在被删除前继续使用 `NANOBOT_*`、`~/.nanobot/` 和 camelCase
> 配置别名——那是尚未改写完的实现，不是兼容承诺。

## 仓库结构（`D00` 已落地，技术方案 §4.1–§4.4）

```text
src/nucleamind/            # 唯一 Python 包（src 布局，强制 editable install）
├── contracts/             # 第 1 层：公开数据契约，纯类型，零内部依赖
├── kernel/                # 第 2 层：机制，只依赖 contracts
├── sdk/                   # 第 3 层：插件唯一依赖面，只 import contracts
├── builtins/              # 第 4 层：内建默认能力，与插件同等身份
├── runtime/               # 第 5 层：组装根 + `nm` 可执行程序
├── embed/                 # 第 5 层：嵌入式 Python SDK
└── legacy/                # 隔离区：nanobot 遗留代码，只出不进
plugins/                   # 一等公民：官方插件，各自独立发行
examples/plugins/          # 教学用最小示例插件
tests/                     # 镜像分层：architecture/ contracts/ kernel/ ... legacy/
deploy/                    # Dockerfile / compose / entrypoint
webui/                     # 前端源码（TypeScript）
```

`contracts/`–`embed/` 目前是空骨架（只有 `__init__.py` 与 docstring），
按开发方案 `D02` 起逐个填充。**新代码直接写在最终位置**，不要放临时目录。

## 开发命令

```bash
# Python：单测 / lint
.venv\Scripts\python.exe -m pytest tests/legacy/test_openai_api.py::test_function -v
.venv\Scripts\python.exe -m ruff check src/ plugins/

# legacy/ 债务指标（只允许下降）
.venv\Scripts\python.exe scripts/legacy_debt.py

# 严格类型检查（与 CI 一致）
uv sync --all-extras --dev
uv run --no-sync python -m scripts.install_channel_dependencies --all-channels
uv run --no-sync basedpyright

# WebUI：dev server（代理 API/WS 到 gateway :8765）/ build / test
# 构建产物输出到 ../src/nucleamind/legacy/web/dist（打进 Python wheel）
cd webui && bun run dev      # 或 NANOBOT_API_URL=... bun run dev
cd webui && bun run build
cd webui && bun run test

# Gateway（迁移期遗留入口，D31 随 legacy/agent/ 一并删除）
nm legacy gateway
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

## 高层架构（`legacy/` 隔离区，源自 nanobot）

下列 `legacy/` 路径均在 `src/nucleamind/legacy/` 之下，描述的是**待迁移**的遗留实现。
新 Kernel 的目标分层见技术方案 §4.2；`legacy/` 的隔离规则见
[`src/nucleamind/legacy/README.md`](./src/nucleamind/legacy/README.md)。

### 核心数据流

消息通过异步 `MessageBus`（`legacy/bus/queue.py`）解耦聊天渠道与 agent 核心：

1. **Channels**（`legacy/channels/`）接收外部平台消息，向总线发布 `InboundMessage` 事件。
2. **`AgentLoop`**（`legacy/agent/loop.py`）消费入站消息，构建上下文，协调整个 turn。
3. **`AgentRunner`**（`legacy/agent/runner.py`）执行真正的 LLM 对话循环：发送消息、接收 tool calls、执行工具、流式返回。
4. 响应以 `OutboundMessage` 事件发布回对应渠道。

### 关键子系统

- **Agent Loop**（`legacy/agent/loop.py`、`runner.py`）：核心处理引擎。`AgentLoop` 管理 session keys、hooks、上下文构建；`AgentRunner` 执行带工具调用的多轮 LLM 对话。
- **LLM Providers**（`legacy/providers/`）：Anthropic、OpenAI 兼容、OpenAI Responses API、Azure、Bedrock、GitHub Copilot、Codex 等，基于公共基类（`base.py`），含图像生成（`image_generation.py`）与音频转录（`transcription.py`）。`factory.py` / `registry.py` 负责实例化与模型发现。
- **Channels**（`legacy/channels/`）：Telegram、Discord、Slack、Feishu、Matrix、WhatsApp、QQ、WeChat、WeCom、DingTalk、Email、MoChat、MS Teams、WebSocket、Mattermost。`manager.py` 通过 `pkgutil` 扫描自动发现，每个 channel 是自包含包。
- **Tools**（`legacy/agent/tools/`）：文件系统、shell（含沙箱后端）、web 搜索/抓取、MCP servers、cron、notebook、subagent、长任务/持续目标（`long_task.py`）、图像生成、自修改。`pkgutil` 扫描 + entry-point 插件自动发现。
- **Memory**（`legacy/agent/memory.py`）：会话历史持久化 + Dream 两阶段记忆整合，原子写（temp + fsync + rename）保证持久性。
- **Session Management**（`legacy/session/`）：会话历史、上下文压缩、TTL 自动压缩（`manager.py`）、持续目标状态（`goal_state.py`）。
- **Config**（`legacy/config/schema.py`、`loader.py`）：Pydantic 配置，从 `~/.nanobot/config.json` 加载（迁移期不变），支持 camelCase 别名。
- **WebUI**（`webui/`）：Vite + React SPA，通过 WebSocket 多路复用协议与 gateway 通信。
- **API Server**（`legacy/api/server.py`）：OpenAI 兼容 HTTP API（`/v1/chat/completions`、`/v1/models`）。
- **Command Router**（`legacy/command/`）：斜杠命令路由与内置命令处理。
- **Skills**（`legacy/skills/`）：内置技能定义（cron、github、image-generation 等），markdown + YAML frontmatter。
- **Security**（`legacy/security/`）：PTH 文件守卫等安全措施，CLI 入口激活。

### 入口点

- **`nm`（唯一命令）**：`src/nucleamind/runtime/cli/main.py`（最小骨架，真正的子命令在 `D23`）
- **遗留 CLI**：`nm legacy` -> `src/nucleamind/runtime/legacy_entry.py` -> `legacy/cli/commands.py`
- **遗留 Python SDK**：`legacy/nanobot.py`（新层门面 `embed/` 为重写，不移植旧实现）

## 架构约束与改造方向

改造时遵循以下边界（详见 [.agent/design.md](.agent/design.md)）；分层与依赖规则
`R1`–`R6` 见技术方案 §3.1、§4.2：

1. **核心保持小，能力在边缘扩展**：新代码写在最终位置——机制进 `kernel/`，能力进 `builtins/` 或 `plugins/`，公开类型进 `contracts/`，装配进 `runtime/`。**不允许往 `legacy/` 新增文件**（只出不进，`R6`）。
2. **接口优先于实现**：不绑定具体数据库、聊天平台、模型供应商、工作流框架，优先设计抽象接口（Memory Interface、Context Interface、Message Interface、Agent Provider Interface）。
3. **机制优先于功能**：核心提供 Extension Mechanism、Lifecycle、Registry、Interface，而不是堆积具体功能。
4. **少结构、多智能**：优先简单可读的代码，不要引入不必要的框架层和间接层。
5. **优先重复而非过早抽象**：channel/provider 之间允许重复逻辑（发送重试、媒体处理、消息拆分），不要为消除重复引入复杂基类。从 `legacy/` 复用实现时**把代码搬到新家并补测试**，不要 import 过来。
6. **在边界类型化动态数据**：wire payload、持久化记录、第三方 SDK 对象在拥有它们的边缘做解析/规范化，用 `TypedDict` 固定形状，不用 `Any` 向核心泄漏；`typing.cast` 必须有运行时检查支撑。
7. **显式优于魔法**：配置必须显式声明（新层在 `kernel/config/`，`legacy/` 仍在 `legacy/config/schema.py`）；错误处理抛清晰异常，不静默修正坏输入。
8. **新模块首个 docstring 含「职责/不负责」两行**（技术方案 §4.6）：`contracts/`、`kernel/`、`sdk/`、`runtime/` 强制，由 `D01` 的架构守卫检查。

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

- `docs/project/开发背景.md` 只维护相对稳定的项目愿景、目标和原则，不记录阶段性进度。
- `docs/project/` 保持扁平，不按方案、计划、决策等类型继续拆分子目录；长期文档使用
  中文原名，临时开发文档文件名优先使用小写英文和短横线。
- 开发模块时，可在 `docs/project/` 直接创建临时 Markdown 文档，记录目标、技术方案、
  任务拆分、风险和验收方式。
- 模块完成后，先把当前状态、关键结果和下一步工作更新到 `docs/project/README.md`，
  再将仍然有效的架构或使用说明更新到正式文档，最后删除对应临时开发文档。
- 参考项目导航资料放在 [`docs/references/`](./docs/references/README.md)，不要写入被
  Git 忽略的 `references/`。

## 指令文件边界

- 根目录 `AGENTS.md` 是本仓库 AI 编码代理的开发指引，`CLAUDE.md` 仅引用本文件。
- `legacy/templates/AGENTS.md` 是运行时复制到用户 workspace 的 Agent 行为模板，不是仓库开发规范。
- 修改 `legacy/templates/`、`legacy/skills/` 中的说明会改变最终用户 Agent 的行为；不要把仓库开发流程、上游协作方式或当前重构任务写入这些运行时模板。

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
