"""常见 Coding Agent 任务的命名能力 Preset。

Preset 控制模型可见的工具集合，并在适用时收紧上下文预算。它不决定写入或 Shell 调用是否
通过审批，那是独立的 `PermissionPolicy` 关注点。
"""

from dataclasses import dataclass
from enum import StrEnum

from minicode_agent.runtime.types import AgentConfig


class AgentPreset(StrEnum):
    """Supported combinations of coding-agent capabilities."""

    MINIMAL = "minimal"
    STANDARD = "standard"
    REVIEW = "review"


@dataclass(frozen=True, slots=True)
class PresetDefinition:
    """绑定到某个 Preset 的静态能力和限制配置。

    `tool_names` 会被 Registry 构建逻辑使用。将工具列表放在数据对象中，可以让 CLI 帮助、
    Web 表单、持久化和 Runtime 共享同一份能力契约。
    """

    name: AgentPreset
    description: str
    tool_names: tuple[str, ...]
    context_token_cap: int | None = None

    def apply(self, config: AgentConfig) -> AgentConfig:
        """Constrain a caller-provided runtime configuration for this preset."""
        if self.context_token_cap is None:
            return config
        return config.model_copy(
            update={"max_context_tokens": min(config.max_context_tokens, self.context_token_cap)}
        )


_PRESETS: dict[AgentPreset, PresetDefinition] = {
    AgentPreset.MINIMAL: PresetDefinition(
        name=AgentPreset.MINIMAL,
        description="Read-only repository inspection with a compact context budget.",
        tool_names=("read_file", "list_files", "search_text"),
        context_token_cap=8_000,
    ),
    AgentPreset.STANDARD: PresetDefinition(
        name=AgentPreset.STANDARD,
        description="Repository changes and shell commands with the selected approval policy.",
        tool_names=("read_file", "list_files", "search_text", "edit_file", "run_shell"),
    ),
    AgentPreset.REVIEW: PresetDefinition(
        name=AgentPreset.REVIEW,
        description="Read-only inspection plus approved shell commands for review and tests.",
        tool_names=("read_file", "list_files", "search_text", "run_shell"),
    ),
}


def get_preset(preset: AgentPreset | str) -> PresetDefinition:
    """Resolve one supported preset or raise a clear error for invalid input."""
    try:
        return _PRESETS[AgentPreset(preset)]
    except ValueError as exc:
        choices = ", ".join(item.value for item in AgentPreset)
        raise ValueError(f"unknown agent preset {preset!r}; expected one of: {choices}") from exc
