# Stream Reasoning Summaries in Chat Completions

## Why

For reasoning models the upstream Responses stream emits
`response.reasoning_summary_text.delta` events (the "thinking" summary), but
the Chat Completions adapter (`iter_chat_chunks` / `collect_chat_completion`)
only forwards `response.output_text.delta`, refusal, and tool-call events. The
reasoning summary is therefore dropped, so OpenAI-compatible clients that
display a model's thinking (for example the Cursor agent) show nothing even
though the request asked for `reasoning.summary`.

## What Changes

- Forward `response.reasoning_summary_text.delta` (and
  `response.reasoning_text.delta`) into the assistant `content` as a
  collapsible Markdown block (`<details><summary>Thinking</summary> …
  </details>`) that precedes the answer.
- Chat-completions clients (notably Cursor) do not render a separate
  `reasoning` field, but they do render `<details>` in message content, so this
  surfaces the thinking trace within the standard Chat Completions contract.
- Apply the same embedding to the non-streaming `chat.completion` message.

## Impact

- Reasoning ("thinking") becomes visible to chat-completions clients that
  render content markdown.
- Additive: the thinking block is emitted only when reasoning text is present,
  so non-reasoning responses are unchanged.
