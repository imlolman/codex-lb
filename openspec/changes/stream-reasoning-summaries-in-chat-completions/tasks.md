## 1. Implementation

- [x] 1.1 Add `reasoning` / `reasoning_content` fields to the chat chunk delta and message models.
- [x] 1.2 Forward `response.reasoning_summary_text.delta` / `response.reasoning_text.delta` as chunk deltas in `iter_chat_chunks`.
- [x] 1.3 Accumulate reasoning onto the non-streaming `chat.completion` message in `collect_chat_completion`.

## 2. Verification

- [x] 2.1 Add unit coverage for reasoning streaming and collection.
- [x] 2.2 Run focused pytest, ruff, and ty.
- [ ] 2.3 Validate OpenSpec once the OpenSpec CLI is available in the workspace.
