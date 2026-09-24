"""Web Console API 和后台运行管理。

这是 Python 后端 bundle。React/Vite 前端位于仓库根目录下独立的 ``web/`` 目录。
"""

from minicode_agent.web.app import create_app
from minicode_agent.web.manager import RunManager

__all__ = ["RunManager", "create_app"]
