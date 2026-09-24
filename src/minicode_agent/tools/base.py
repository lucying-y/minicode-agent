"""结构化工具的基类。

每个工具暴露一个 Pydantic 输入模型和声明的权限级别。Registry 会在调用 `run()` 前完成
参数校验与授权，因此工具实现可以专注于单一操作，并返回与 Provider 无关的 `ToolResult`。
"""

from abc import ABC, abstractmethod

from pydantic import BaseModel

from minicode_agent.runtime.types import ToolResult
from minicode_agent.security import PermissionLevel, Workspace


class Tool[InputT: BaseModel](ABC):
    """校验输入后执行单个工作区操作。

    工具类有意保持精简，不应决定审批策略或序列化事件；这些横切关注点属于 Registry 和
    Hook 层。
    """

    name: str
    description: str
    permission: PermissionLevel
    input_model: type[InputT]

    @abstractmethod
    async def run(self, data: InputT, workspace: Workspace) -> ToolResult:
        """执行已经通过校验的工具请求。"""
        raise NotImplementedError
