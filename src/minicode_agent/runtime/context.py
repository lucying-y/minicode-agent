"""Deterministic context budgeting for model requests.

The runtime deliberately uses a provider-independent character estimate instead
of importing a tokenizer for one particular model.  The estimate is only a
budgeting guardrail; the provider remains responsible for its actual context
window.  The important invariant here is that an assistant message containing
tool calls is kept together with the following tool results.
"""

from minicode_agent.runtime.types import Message


class ContextManager:
    """Keep the task and newest complete assistant/tool turns within a token estimate.

    A conversation is trimmed from the oldest completed execution block first.
    The initial system prompt, the original task, and the current user turn are
    always preferred over older history because they define the active request.
    """

    def __init__(self, max_tokens: int) -> None:
        if max_tokens < 128:
            raise ValueError("max_tokens must be at least 128")
        self.max_tokens = max_tokens

    @staticmethod
    def estimate_tokens(messages: list[Message]) -> int:
        """Estimate tokens conservatively without provider-specific tokenizers."""
        characters = sum(len(message.model_dump_json()) for message in messages)
        return max(1, (characters + 3) // 4)

    def prepare(self, messages: list[Message]) -> list[Message]:
        """Return the messages that fit the budget without mutating the caller list.

        The method treats every assistant message as the start of an execution
        block.  Any following tool messages belong to that block, so a trim can
        never leave a tool result whose `tool_call_id` has been removed.
        """
        if len(messages) <= 2 or self.estimate_tokens(messages) <= self.max_tokens:
            return list(messages)

        base = list(messages[:2])
        latest_user_index = next(
            (
                index
                for index in range(len(messages) - 1, 1, -1)
                if messages[index].role == "user"
            ),
            len(messages),
        )
        current_turn = list(messages[latest_user_index:])
        blocks = self._conversation_blocks(messages[2:latest_user_index])
        kept: list[list[Message]] = []

        for block in reversed(blocks):
            # Build the candidate in chronological order while considering the
            # newest block first.  Once one older block does not fit, no still
            # older block can fit without also removing a newer block.
            ordered_kept = [message for existing in reversed(kept) for message in existing]
            candidate = base + block + ordered_kept + current_turn
            if self.estimate_tokens(candidate) > self.max_tokens:
                break
            kept.append(block)

        ordered = [message for block in reversed(kept) for message in block]
        omitted = len(messages) - len(base) - len(ordered) - len(current_turn)
        if omitted:
            # The marker is useful to the model, but it is optional: keeping a
            # valid conversation is more important than spending the last few
            # budgeted tokens on explanatory metadata.
            marker = Message(
                role="system",
                content=f"[Context manager omitted {omitted} older execution messages.]",
            )
            if self.estimate_tokens(base + [marker] + ordered + current_turn) <= self.max_tokens:
                return base + [marker] + ordered + current_turn
        return base + ordered + current_turn

    @staticmethod
    def _conversation_blocks(messages: list[Message]) -> list[list[Message]]:
        blocks: list[list[Message]] = []
        for message in messages:
            if message.role == "assistant" or not blocks:
                blocks.append([message])
            else:
                blocks[-1].append(message)
        return blocks
