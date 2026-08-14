# plugins/ — 官方插件

每个官方插件是**独立发行包**，目录形如：

```text
plugins/nucleamind-plugin-<id>/
├── pyproject.toml
├── src/nucleamind_plugin_<id>/
└── tests/
```

放在仓库顶层而不是包内，是为了让边界由打包机制强制：包内的「插件」可以随手
import 兄弟模块，依赖规则 `R4` 就成了空话。官方插件与第三方插件走**完全相同**
的加载路径（entry point 组 `nucleamind.plugins`）。

写插件请看 [`docs/plugin-development.md`](../docs/plugin-development.md)，可运行的最小范例在
[`examples/plugins/`](../examples/plugins/README.md)。

## 当前的官方插件

| 目录 | id | 能力 | 落地于 |
| --- | --- | --- | --- |
| `nucleamind-plugin-openai-api/` | `openai-api` | `CHANNEL:openai` —— OpenAI 兼容 HTTP 接口（`/v1/chat/completions`、`/v1/models`），配合 `nm serve` 常驻 | `D31` |
| `nucleamind-plugin-anthropic/` | `anthropic` | `MODEL:anthropic` —— Anthropic 原生 Messages API，与内建 `model-openai` 并存 | `D32` |
| `nucleamind-plugin-discord/` | `discord` | `CHANNEL:discord` —— Discord bot，配合 `nm serve` 常驻 | `D33` |

**它们必须真的装进环境才会被发现**（entry point 没有第二条路）：

```bash
pip install --no-deps -e plugins/nucleamind-plugin-openai-api
pip install --no-deps -e plugins/nucleamind-plugin-anthropic
pip install --no-deps -e plugins/nucleamind-plugin-discord
```

装上不等于启用——`plugins.enabled` 是唯一闸门，改完要重启实例。

