"""Deterministic context budgeting for model requests."""

from minicode_agent.runtime.types import Message


class ContextManager:
    """Keep the task and newest complete assistant/tool turns within a token estimate."""

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
            ordered_kept = [message for existing in reversed(kept) for message in existing]
            candidate = base + block + ordered_kept + current_turn
            if self.estimate_tokens(candidate) > self.max_tokens:
                break
            kept.append(block)

        ordered = [message for block in reversed(kept) for message in block]
        omitted = len(messages) - len(base) - len(ordered) - len(current_turn)
        if omitted:
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
