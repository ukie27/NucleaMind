# 快速上手

从零到第一次对话，再到装上第一个插件。

这篇讲**怎么把 NucleaMind 跑起来**。字段含义与优先级见
[`configuration.md`](./configuration.md)，命令的完整参数见 [`cli.md`](./cli.md)，
容器与常驻部署见 [`deployment.md`](./deployment.md)。

## 1. 安装

需要 Python 3.11 或更新。**NucleaMind 没有发布到 PyPI**——从 PyPI 装 `nanobot-ai` 装到的
是上游项目，不是本仓库。从本地检出装：

```bash
git clone <本仓库地址> NucleaMind
cd NucleaMind

python -m venv .venv
.venv/bin/python -m pip install -e .          # Windows：.venv\Scripts\python.exe
```

装完之后 `nm` 就在虚拟环境的 `bin/`（Windows 是 `Scripts\`）里：

```bash
nm --version
nm --help
```

宿主只有四个第三方依赖（pydantic / httpx / jsonschema / packaging）。**能力所需的包由
那个能力自己的发行包声明**，不回到宿主——所以上面这一条命令装完就能用，官方插件按需再装
（见第 5 节）。

## 2. 生成配置

```bash
nm init
```

它在实例目录里建两个文件，**已经存在的 `config.json` 一个字节都不会动**：

```text
~/.nucleamind/default/
├── config.json          # 你的配置，只有 nm init 建它、只有 nm plugins enable 改它
└── config.schema.json   # 派生的 JSON Schema，供编辑器补全，运行期忽略
```

生成的 `config.json` 只有你真的要改的几个键：

```json
{
  "$schema": "./config.schema.json",
  "model": {
    "provider": "openai",
    "name": "gpt-4o-mini"
  },
  "plugins": {
    "model-openai": {
      "secrets": {
        "api_key": "${OPENAI_API_KEY}"
      }
    }
  }
}
```

其余四十多个字段都有默认值，不写进模板是刻意的：全倒进去会让它们变成你不敢动的噪声，
而且每一个都会被 `nm config show --origins` 记成「来自 config.json」，
「我改过什么」这个问题就永远答不上来了。

## 3. 给上模型凭据

配置文件里**只有变量名，没有凭据本身**。`${OPENAI_API_KEY}` 是一个引用，值在环境变量里：

```bash
export OPENAI_API_KEY=sk-...        # Windows：set OPENAI_API_KEY=sk-...
```

`nm init` 的输出会告诉你还差哪个变量。凭据引用的完整语义（没有 `${VAR:-默认值}` 回退、
没有转义、空变量按缺失处理）见 [`configuration.md` 的 `${VAR}` 一节](./configuration.md#5-var-凭据引用)。

**用本地模型服务不需要凭据。** Ollama / vLLM / LM Studio 都是 OpenAI 兼容接口，
把内建 provider 指过去、把鉴权关掉即可：

```json
{
  "model": { "provider": "openai", "name": "qwen2.5:7b" },
  "plugins": {
    "model-openai": {
      "config": { "base_url": "http://127.0.0.1:11434/v1", "auth": "none" }
    }
  }
}
```

## 4. 第一次对话

```bash
nm run
```

进入交互式会话：每行输入是一轮对话，`Ctrl-C` 中断当前这一轮并继续，再按一次退出；
输入 `/exit` 或 `/quit` 也可以退出。

跑一条就退出用 `-p`（退出码反映这一轮的终态：`0` 正常、`130` 被中断、`1` 失败）：

```bash
nm run -p "用一句话介绍你自己"
```

试试内建命令——它们和插件提供的命令走完全同一条分流路径：

```text
> /help
> /capabilities
> /config
```

零配置下已经可用的内建能力有六件：会话存储、上下文组装、OpenAI 兼容模型、
文件工具（`fs.read` / `write` / `edit` / `list` / `grep`）、shell 工具（`shell.exec`）、
命令集（`/help` `/config` `/session` `/plugins` `/capabilities` `/cancel`）。

## 5. 装一个官方插件

官方插件是**独立发行包**，靠 entry point 被发现，所以**必须真的装进环境**：

```bash
.venv/bin/python -m pip install -e plugins/nucleamind-plugin-web
```

装进环境**不等于启用**（`DST-002`：安装 ≠ 启用）。没有写进 `plugins.enabled` 的候选
连 manifest 都不会被读——这既是安全边界，也是启动开销的边界：

```bash
nm plugins list          # 看看发现了哪些、状态是什么
nm plugins enable web    # 写进 config.json 的 plugins.enabled（下次启动生效）
```

然后确认它真的生效了：

```bash
nm capabilities          # 生效 / 被覆盖 / 已禁用 / 冲突，四段都印
```

九个官方插件（`--no-deps` 是刻意的，平台 SDK 由你按需另装）：

```bash
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-openai-api
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-anthropic
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-discord
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-feishu
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-web
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-image
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-mcp
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-memory
.venv/bin/python -m pip install --no-deps -e plugins/nucleamind-plugin-cron
```

每个插件自己带一份 README（配置表 + 已知边界 + 刻意不做的事），清单见
[`plugins/README.md`](../plugins/README.md)。

## 6. 权限

插件第一次被加载时，它 manifest 里声明的权限会被整份记进
`~/.nucleamind/default/permissions.json`（首见即授予，TOFU）。此后插件**扩大**声明时，
新增的那几项默认落在 `pending`（也就是拒绝），要你显式批准：

```bash
nm permissions list
nm permissions grant web net "抓网页"
```

**应用级权限不是进程隔离**——同进程的插件可以绕过全部门面直接 `import os`。
这句话在 [`permissions.md`](./permissions.md) 里写得更完整，装第三方插件之前读一下那篇。

## 7. 常驻跑一个 Channel

`nm run` 把进程交给 CLI 入口，在 `nohup` / systemd 下没有意义。要常驻的是 `nm serve`：

```bash
.venv/bin/python -m pip install -e plugins/nucleamind-plugin-openai-api
nm plugins enable openai-api
nm serve                      # 默认监听 127.0.0.1:8760
```

它启动全部已启用的 Channel 能力并等信号。Discord、飞书、cron 调度器用的是同一条命令
——不为某个插件写第二条。容器与 systemd 见 [`deployment.md`](./deployment.md)。

## 下一步

| 想干的事 | 去哪 |
| --- | --- |
| 查某个配置字段是什么意思 | [`configuration.md`](./configuration.md) |
| 查某条命令的参数与退出码 | [`cli.md`](./cli.md) |
| 部署成常驻服务 | [`deployment.md`](./deployment.md) |
| 写一个自己的插件 | [`plugin-development.md`](./plugin-development.md) |
| 理解权限模型 | [`permissions.md`](./permissions.md) |
| 读或迁移会话存储 | [`session-storage.md`](./session-storage.md) |
