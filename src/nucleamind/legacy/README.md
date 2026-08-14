# legacy/ — 遗留隔离区

本目录是原 nanobot 代码的**剩余部分**（`D31` 之后 225 文件 / 77040 行），由开发方案
`D00` 从仓库根的 `nanobot/` 整体 `git mv` 而来。它**不是「以后再说」的垃圾桶**，
而是有明确规则的隔离区。

**`D31` 之后它没有任何入口能启动**：遗留 Agent 路径（`agent/`、`cli/`、`webui/`、
`gateway/`、`api/`、`sdk/`、`triggers/` 与 `nanobot.py`、`__main__.py`）已经删除，
`nm legacy` 与 `runtime/legacy_entry.py` 一并删除。剩下的是不依赖 agent 的库代码，
留在树里只有一个用途：`D32+` 把能力迁成插件时的**在树参考**。

## 隔离规则（技术方案 §4.3）

1. **只出不进**：不允许新增文件，不允许新功能进入（`R6` 由 `tests/architecture/` 强制）。
2. **依赖单向**：新代码不 import `legacy/`；`legacy/` 可以 import 新代码（适配层方向）。
   **`D31` 之后 `R6` 没有例外**——那个过渡适配器已经删掉，守卫的断言是「一处也没有」。
3. **进度可度量**：`scripts/legacy_debt.py` 统计本目录的文件数与行数，这个数字
   只允许下降——上升即说明有人在往隔离区加东西。
4. **迁移即删除**：一个能力迁到 `plugins/` 或 `builtins/` 后，本目录中的对应
   目录在同一个 PR 内删除，不留「以后再清」的副本。

需要复用遗留实现（如路径守卫、原子写）时，**把代码搬到新家并补测试**，
不要 import 过来。短期有重复，但本目录能干净删除。

## 迁移期的运行契约

`D00` 只做受限的结构与命名迁移。本目录内部**继续**使用自己的旧契约，这不是
新架构的兼容承诺：

| 项 | `legacy/` 迁移期 | 新层（contracts/kernel/...） |
| --- | --- | --- |
| 环境变量前缀 | `NANOBOT_` | 只用 `NUCLEAMIND_` |
| 实例目录 | `~/.nanobot/` | `~/.nucleamind/<instance>/` |
| 配置键风格 | camelCase 别名 | 只用 snake_case |

新层**不双读**旧格式、不写长期兼容垫片（技术方案 §4.5）。旧实例目录里的数据
仍在磁盘上，需要时手工拷贝配置即可。

面向用户的帮助文本、User-Agent、`owned_by` 等字符串里仍然写着 `nanobot`。
这些是历史叙述，不在 `D00` 的改动范围内，随本目录一起删除。

## 入口

**没有入口。** `D31` 删掉了 `nm legacy`、`legacy/__main__.py` 与 gateway，
本目录的代码此后只能被读，不能被运行。要跑 Agent 用 `nm run` / `nm serve`。

## 迁移状态

- `D00`：全部内容搬入本目录（352 文件 / 133317 行）。
- `D31`：删除遗留 Agent 路径——`agent/`、`cli/`、`webui/`、`gateway/`、`api/`、`sdk/`、
  `triggers/`、`nanobot.py`、`__main__.py`、`channels/websocket/`，以及
  `session/webui_turns.py`、`cron/{bound_runner,webui_metadata}.py`、
  `utils/progress_events.py`。降到 225 文件 / 77040 行。
  剩余部分中 **`providers/` 与 `channels/` 是 `D32+` 的主要迁移源**。

后续每完成一个能力模块，在此更新已删除的子目录列表。
