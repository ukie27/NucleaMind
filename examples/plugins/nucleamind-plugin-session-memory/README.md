# nucleamind-plugin-session-memory

NucleaMind 的**覆盖内建能力**示例：用一个纯内存的 `SessionStore` 覆盖内建的 JSONL 会话
存储。进程退出即忘——适合一次性容器、演示，以及「不要在磁盘上留下对话」的场景。

它演示 `echo-tool` 覆盖不到的三件事：

1. **SINGLETON 能力的覆盖**：`session_store` 全实例只有一个生效实现，替换必须在 manifest
   里显式写 `overrides = "builtin:jsonl"`。覆盖永不由加载顺序决定（`EDG-102`）。
2. **覆盖关系是可见的**：`nm capabilities` 的「被覆盖」段会印出
   `session_store:jsonl ← builtin` 与覆盖它的 `session_store:memory ← plugin:session-memory`。
   静默替换用户的会话历史后端是这套设计明确要堵的路。
3. **禁用之后的语义由配置决定**（见下）。

## 安装与启用

```bash
pip install -e examples/plugins/nucleamind-plugin-session-memory
```

```json
{
  "plugins": { "enabled": ["session-memory"] }
}
```

## 禁用它：`on_disable` 必须显式写

把它写进 `plugins.disable` 时，还必须回答一个问题——被它顶掉的内建存储要不要回来：

```json
{
  "plugins": {
    "enabled": ["session-memory"],
    "disable": ["session-memory"],
    "session-memory": { "on_disable": "restore_builtin" }
  }
}
```

| 取值 | 结果 |
| --- | --- |
| `restore_builtin` | 内建 JSONL 存储重新生效，会话继续落盘 |
| `leave_missing` | 会话存储保持缺失，实例以 `CAPABILITY_MISSING` 拒绝启动 |
| 不写 | **配置错误**（`CONFIG_INVALID`），指向 `/plugins/session-memory/on_disable` |

不写就报错看起来严格，但它兑现的是 `BAS-004`：Kernel 不得在一项内建能力被覆盖后**隐式**
把它恢复回来。用户可能正是因为不再想让对话落盘才装的这个插件；关掉它之后历史悄悄回到
磁盘上，等于替他做了一个关于数据的决定。

完整的插件开发说明见仓库的
[`docs/plugin-development.md`](../../../docs/plugin-development.md)。
