## ADDED Requirements

### Requirement: Accept Responses-style bodies on Chat Completions
The service MUST accept `POST /v1/chat/completions` requests whose body uses the OpenAI Responses request shape — an `input` field and no `messages` array — and MUST normalize that body into Chat Completions semantics before validation. Normalization MUST only run when `messages` is absent (or empty) and `input` is present, so standard Chat Completions requests are unaffected. The response MUST remain on the Chat Completions contract (`chat.completion` or `chat.completion.chunk`).

#### Scenario: Responses-style body with string input
- **WHEN** the client sends `{ "model": "gpt-5.5", "input": "hi", "user": "abc" }`
- **THEN** the service maps `input` to a `user` message, drops the unsupported `user` field, and begins a Chat Completions response

#### Scenario: Standard chat request is untouched
- **WHEN** the client sends a body that already contains a non-empty `messages` array
- **THEN** the service does not apply Responses-style normalization and validates the request as a Chat Completions request

#### Scenario: Invalid after normalization
- **WHEN** a Responses-style body normalizes to an empty `messages` list
- **THEN** the service returns a 4xx response with an OpenAI error envelope

### Requirement: Map Responses input items to chat messages
When normalizing a Responses-style body, the service MUST map `input` items to Chat Completions messages: role items (`system`, `developer`, `user`, `assistant`) with string or Responses content parts (`input_text`, `output_text`, `input_image`) MUST become the corresponding chat messages; `function_call` items MUST become an assistant message with `tool_calls`; `function_call_output` items MUST become `tool` messages carrying the matching `tool_call_id`; and `reasoning` items MUST be dropped. A top-level `instructions` string MUST be merged as a leading `system` message.

#### Scenario: Tool call round-trip
- **WHEN** the `input` contains a `function_call` item followed by a `function_call_output` item that share a `call_id`
- **THEN** the normalized messages contain an assistant message whose `tool_calls[].id` equals that `call_id` and a `tool` message whose `tool_call_id` equals that `call_id`

#### Scenario: Instructions become a system message
- **WHEN** the body includes a top-level `instructions` string and an `input` user item
- **THEN** the normalized messages begin with a `system` message containing the instructions followed by the user message

### Requirement: Normalize Responses fields to chat fields
When normalizing a Responses-style body, the service MUST convert flat Responses function tool definitions (`{"type":"function","name":...,"parameters":...}`) to the nested Chat Completions `function` form, forward the `reasoning` object unchanged (preserving both `effort` and `summary`), map `max_output_tokens` to `max_tokens`, and map `text.format` to `response_format`. Responses-only fields that have no Chat Completions equivalent (for example `user`, `store`, `previous_response_id`) MUST be dropped rather than forwarded upstream.

#### Scenario: Flat tool normalized to nested function form
- **WHEN** the body includes `tools=[{"type":"function","name":"do_it","parameters":{...}}]`
- **THEN** the normalized request includes `tools=[{"type":"function","function":{"name":"do_it","parameters":{...}}}]`

#### Scenario: Reasoning object forwarded
- **WHEN** the body includes `reasoning={"effort":"high","summary":"auto"}`
- **THEN** the normalized request carries the same `reasoning` object so the upstream streams reasoning summaries
