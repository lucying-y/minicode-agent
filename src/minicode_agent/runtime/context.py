"""模型请求的确定性上下文预算。

Runtime 有意使用与 Provider 无关的字符估算，而不是为某个模型引入专用 tokenizer。这个
估算只是预算保护，实际上下文窗口仍由 Provider 负责。这里最重要的不变量是：包含工具调用
的 assistant 消息必须与后续工具结果一起保留。
"""

from minicode_agent.runtime.types import Message


class ContextManager:
    """在 Token 估算范围内保留任务以及最新完整的 assistant/tool 轮次。

    对话会优先从最早完成的执行块开始裁剪。初始 system prompt、原始任务和当前用户轮次
    定义了正在处理的请求，因此它们始终优先于更早的历史。
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
        """返回适合预算且不修改调用方列表的消息。

        方法将每条 assistant 消息视为执行块的开始，后续工具消息都属于该块。因此裁剪后
        不会留下已经移除其 `tool_call_id` 的工具结果。
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
            # 在从最新块开始考虑时，仍按时间顺序构建候选消息。一旦某个更早的块放不下，更早
            # 的块也不可能在保留更新块的前提下放入预算。
            ordered_kept = [message for existing in reversed(kept) for message in existing]
            candidate = base + block + ordered_kept + current_turn
            if self.estimate_tokens(candidate) > self.max_tokens:
                break
            kept.append(block)

        ordered = [message for block in reversed(kept) for message in block]
        omitted = len(messages) - len(base) - len(ordered) - len(current_turn)
        if omitted:
            # 省略标记对模型有帮助，但它不是必需的：保持对话协议有效比用最后几个预算 Token
            # 添加说明元数据更重要。
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
