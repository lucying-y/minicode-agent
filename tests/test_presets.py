from pathlib import Path

import pytest

from minicode_agent.runtime import AgentConfig, AgentPreset, get_preset
from minicode_agent.tools import create_default_registry


@pytest.mark.parametrize(
    ("preset", "tool_names"),
    [
        (AgentPreset.MINIMAL, {"read_file", "list_files", "search_text"}),
        (
            AgentPreset.STANDARD,
            {"read_file", "list_files", "search_text", "edit_file", "run_shell"},
        ),
        (AgentPreset.REVIEW, {"read_file", "list_files", "search_text", "run_shell"}),
    ],
)
def test_preset_selects_intended_default_tools(
    tmp_path: Path,
    preset: AgentPreset,
    tool_names: set[str],
) -> None:
    definition = get_preset(preset)

    registry = create_default_registry(tmp_path, allowed_tools=set(definition.tool_names))

    assert {schema.name for schema in registry.schemas()} == tool_names


def test_minimal_preset_caps_context_without_overriding_smaller_callers_limit() -> None:
    minimal = get_preset(AgentPreset.MINIMAL)

    assert minimal.apply(AgentConfig(max_context_tokens=32_000)).max_context_tokens == 8_000
    assert minimal.apply(AgentConfig(max_context_tokens=1_024)).max_context_tokens == 1_024


def test_standard_preset_keeps_requested_context_limit() -> None:
    config = AgentConfig(max_context_tokens=48_000)

    assert get_preset(AgentPreset.STANDARD).apply(config) is config


def test_unknown_preset_and_tool_names_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="unknown agent preset"):
        get_preset("missing")
    with pytest.raises(ValueError, match="unknown default tool names: unknown"):
        create_default_registry(tmp_path, allowed_tools={"unknown"})
