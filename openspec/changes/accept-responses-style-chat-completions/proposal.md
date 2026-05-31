# Accept Responses-Style Bodies on Chat Completions

## Why

Some OpenAI-compatible clients (notably the Cursor IDE agent) reuse a `/v1`
base URL but POST a **Responses-API-shaped** body to `/v1/chat/completions`:
the payload carries `input` instead of `messages`, flat Responses tool
definitions (`{"type":"function","name":...,"parameters":...}`), an
`instructions` field, a `reasoning` object, and Responses-only fields such as
`user`. Because `/v1/chat/completions` requires a `messages` array, these
requests fail validation with `invalid_request_error` / `param: "messages"`
before reaching the upstream account pool, so the client cannot use the proxy
at all.

The Codex backend only accepts the strict Responses shape that the existing
chat→responses mapping already produces, so the fix is to normalize the
Responses-style chat body back into Chat Completions semantics and let the
proven `to_responses_request()` path handle it.

## What Changes

- Detect Responses-style bodies on `/v1/chat/completions` (an `input` field
  with no `messages`) and normalize them into the Chat Completions request
  shape before validation.
- Map `input` items to `messages`: role messages (with string or
  Responses content parts), `function_call` items to assistant `tool_calls`,
  and `function_call_output` items to `tool` messages; merge top-level
  `instructions` into a leading `system` message; drop `reasoning` items.
- Normalize flat Responses tool definitions to the nested Chat Completions
  `function` form, map `reasoning.effort` to `reasoning_effort`,
  `max_output_tokens` to `max_tokens`, and `text.format` to
  `response_format`, and drop Responses-only fields such as `user`.
- Keep the response on the Chat Completions contract (`chat.completion` /
  `chat.completion.chunk`) so clients posting to `/chat/completions` get the
  response shape they expect.

## Impact

- Lets Responses-style OpenAI-compatible clients (e.g. Cursor) use
  `/v1/chat/completions` against the account pool.
- Purely additive: standard Chat Completions requests with `messages` are
  unchanged because normalization only runs when `messages` is absent and
  `input` is present.
- No change to `/v1/responses` or the upstream wire contract.
