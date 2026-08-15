# NucleaMind Technical Documentation

本目录只放**当前实现**的文档。`D35` 删掉 `legacy/` 的同一个 PR 里，21 篇描述被继承的
nanobot 实现的文档一并删除——它们教人跑的是 `nanobot onboard`、`nanobot webui` 这类
已经不存在的命令，留着比没有更糟。需要确认旧行为时读 `references/nanobot/`
（见 [`references/README.md`](./references/README.md)）。

新层的**用户**文档（安装、配置字段、CLI 参考、部署）尚未写。当前的权威来源是代码本身与
`nm` 的内置帮助：`nm init` 生成一份带 `$schema` 的 `config.json`，`nm --help` 列出全部
子命令，`nm capabilities` 说明哪些能力真的生效了。

## 现有文档

| 目标 | 文档 |
|---|---|
| 了解项目方向 | [`project/开发背景.md`](./project/开发背景.md) |
| 遵循仓库开发规则 | [`../AGENTS.md`](../AGENTS.md) |
| 接手当前开发工作 | [`project/README.md`](./project/README.md) |
| 参考项目的阅读规范 | [`references/README.md`](./references/README.md) |
| 写一个插件 | [`plugin-development.md`](./plugin-development.md) |
| 理解插件权限模型 | [`permissions.md`](./permissions.md) |
| 读或迁移内建会话存储格式 | [`session-storage.md`](./session-storage.md) |

三篇能力文档各自的性质：

- [`session-storage.md`](./session-storage.md) 是**已发布的兼容契约**（`SES-006`），
  外部实现按它写；改 `builtins/session_jsonl/codec.py` 的字段就得改它。
- [`permissions.md`](./permissions.md) 记着 `permissions.json` 的文件格式，以及那句必须
  保留的诚实声明——**应用级权限不是进程隔离**。
- [`plugin-development.md`](./plugin-development.md) 的代码块由
  `tests/e2e/test_plugin_docs.py` **直接执行**，因此不会漂移。

官方插件各自带 README，说明自己的配置项与已知边界：
[`plugins/README.md`](../plugins/README.md)。

## 文档规则

- 不把 NucleaMind 用户指向上游 nanobot 的安装器、PyPI 包、issue、PR、release
  或社区渠道。
- 上游归属记在 `LICENSE`、`THIRD_PARTY_NOTICES.md` 或明确的历史说明里，
  不作为本项目的当前归属。
- 一条能力以插件形态落地时，在同一个 PR 里写它的文档；**不要**先留一篇描述
  「将来会怎样」的占位文档。
- 所有权边界移进或移出 Kernel 时更新架构说明（当前在
  [`project/technical-design.md`](./project/technical-design.md)）。
