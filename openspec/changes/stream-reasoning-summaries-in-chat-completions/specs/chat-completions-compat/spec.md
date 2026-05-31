## ADDED Requirements

### Requirement: Surface reasoning summaries in Chat Completions
The service MUST forward upstream reasoning-summary stream events
(`response.reasoning_summary_text.delta` and `response.reasoning_text.delta`)
to Chat Completions clients by embedding the reasoning text inside the
assistant `content` as a collapsible Markdown block
(`<details><summary>Thinking</summary> … </details>`). The block MUST precede
the visible answer content and MUST be closed before the first answer token (or
at completion if no answer follows). When the stream contains no reasoning
events, no thinking block MUST be emitted. This applies to both streaming
(`chat.completion.chunk`) and non-streaming (`chat.completion`) responses.

#### Scenario: Reasoning summary rendered as a thinking block
- **WHEN** the upstream stream emits `response.reasoning_summary_text.delta` events followed by `response.output_text.delta` events
- **THEN** the chat content opens with `<details><summary>Thinking</summary>`, contains the reasoning text, closes the block, and then streams the answer content

#### Scenario: Non-streaming reasoning embedded in content
- **WHEN** a non-streaming chat request produces reasoning summary deltas upstream
- **THEN** the returned `chat.completion` message content begins with the collapsible thinking block followed by the answer

#### Scenario: No thinking block without reasoning
- **WHEN** the upstream stream contains no reasoning events
- **THEN** the chat content contains no `<details>` thinking block
