"""Application-level permission controls.

This bundle combines approval policy with canonical workspace path validation;
neither should be mistaken for an operating-system sandbox.
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
