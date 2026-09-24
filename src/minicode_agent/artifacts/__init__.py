"""Structured artifacts derived from repository runs.

The public exports summarize workspace changes and test commands without
coupling Runtime to a particular UI.
"""

from minicode_agent.artifacts.git_changes import WorkspaceChangeTracker
from minicode_agent.artifacts.test_results import extract_test_result

__all__ = ["WorkspaceChangeTracker", "extract_test_result"]
