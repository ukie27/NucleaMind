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

本目录当前为空。插件运行时已由开发方案 `D25`–`D30` 落地（写插件请看
[`docs/plugin-development.md`](../docs/plugin-development.md)，可运行的最小范例在
[`examples/plugins/`](../examples/plugins/README.md)），首批官方插件在 `D32+` 的能力
插件化阶段立项。
