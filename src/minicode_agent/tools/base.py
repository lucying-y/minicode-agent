"""Base class for structured tools.

Each tool exposes a Pydantic input model and a declared permission level.  The
registry performs validation and authorization before calling `run()`, so tool
implementations can focus on one operation and return a provider-neutral
`ToolResult`.
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from minicode_agent.runtime.types import ToolResult
from minicode_agent.security import PermissionLevel, Workspace


class Tool[InputT: BaseModel](ABC):
    """Validate input before performing one workspace operation.

    Tool classes are intentionally small.  They should not decide approval
    policy or serialize events; those cross-cutting concerns belong to the
    Registry and Hook layers.
    """

    name: str
    description: str
    permission: PermissionLevel
    input_model: type[InputT]

    @abstractmethod
    async def run(self, data: InputT, workspace: Workspace) -> ToolResult:
        """Execute a validated tool request."""
        raise NotImplementedError
