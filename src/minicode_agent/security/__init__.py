"""应用层权限控制。

此 bundle 将审批策略与工作区规范路径校验组合在一起；二者都不能替代操作系统级沙箱。
"""

from minicode_agent.security.policy import (
    ApprovalHandler,
    ApprovalMode,
    PermissionDenied,
    PermissionLevel,
    PermissionPolicy,
)
from minicode_agent.security.workspace import Workspace, WorkspaceViolation, is_sensitive_path

__all__ = [
    "ApprovalHandler",
    "ApprovalMode",
    "PermissionDenied",
    "PermissionLevel",
    "PermissionPolicy",
    "Workspace",
    "WorkspaceViolation",
    "is_sensitive_path",
]
