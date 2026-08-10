"""第 5 层：嵌入式 Python SDK，runtime 的薄门面。

职责：向外部 Python 代码暴露 RunResult / StreamEvent / SessionSnapshot 等
最小调用面，只包装 runtime/instance.py。
不负责：插件接口（见 nucleamind.sdk），也不重新实现编排逻辑。

本目录当前为空骨架，具体门面由开发方案 D23 落地。
"""
