"""从仓库任务中提取结构化产物。

这里导出的接口用于汇总工作区变更和测试命令，同时避免 Runtime 与特定 UI 耦合。
"""

from minicode_agent.artifacts.git_changes import WorkspaceChangeTracker
from minicode_agent.artifacts.test_results import extract_test_result

__all__ = ["WorkspaceChangeTracker", "extract_test_result"]
