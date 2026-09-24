"""MiniCode Agent 根包。

根包有意只暴露版本号。Runtime、模型、工具、安全、执行、持久化、评测和 Web API
应从各自的 bundle 导入，以便代码中的依赖方向保持清晰可见。
"""

__version__ = "0.1.0"
