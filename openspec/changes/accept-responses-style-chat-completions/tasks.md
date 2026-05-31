## 1. Implementation

- [x] 1.1 Add a Responses-style → Chat Completions normalizer module.
- [x] 1.2 Run the normalizer from a `ChatCompletionsRequest` before-validator when `input` is present and `messages` is absent.
- [x] 1.3 Map `input` items (role messages, `function_call`, `function_call_output`), `instructions`, flat tools, `reasoning.effort`, `max_output_tokens`, and `text.format`; drop Responses-only fields such as `user`.

## 2. Verification

- [x] 2.1 Add unit coverage for the normalizer (messages, tool calls, tools, dropped fields).
- [x] 2.2 Add integration coverage that `/v1/chat/completions` accepts a Cursor-style Responses body.
- [x] 2.3 Run focused pytest, ruff, and ty.
- [ ] 2.4 Validate OpenSpec once the OpenSpec CLI is available in the workspace.
