"""第 3 层：插件 SDK，插件的唯一依赖面。

职责：暴露 NucleaAPI Protocol、PluginManifest、SDK_VERSION 与公开测试夹具；
`__all__` 是对外的规范性稳定清单。
不负责：嵌入式调用（见 nucleamind.embed）、宿主侧实现（见 kernel/plugins）。

本目录当前为空骨架，具体内容由开发方案 D05 落地。
"""
