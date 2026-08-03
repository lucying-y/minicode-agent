"""Web Console API and background run management."""

from minicode_agent.web.app import create_app
from minicode_agent.web.manager import RunManager

__all__ = ["RunManager", "create_app"]
