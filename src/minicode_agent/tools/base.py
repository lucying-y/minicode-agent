"""Base class for structured tools."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from pydantic import BaseModel

from minicode_agent.runtime.types import ToolResult
from minicode_agent.security import PermissionLevel, Workspace

InputT = TypeVar("InputT", bound=BaseModel)


class Tool(ABC, Generic[InputT]):
    """Validate input before performing one workspace operation."""

    name: str
    description: str
    permission: PermissionLevel
    input_model: type[InputT]

    @abstractmethod
    async def run(self, data: InputT, workspace: Workspace) -> ToolResult:
        """Execute a validated tool request."""
        raise NotImplementedError

