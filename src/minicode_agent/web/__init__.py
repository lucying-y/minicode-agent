"""Web Console API and background run management.

This is the Python backend bundle. The React/Vite frontend lives in the separate
root-level ``web/`` directory.
"""

from minicode_agent.web.app import create_app
from minicode_agent.web.manager import RunManager

__all__ = ["RunManager", "create_app"]
