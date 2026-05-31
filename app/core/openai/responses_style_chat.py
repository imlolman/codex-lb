"""Normalize Responses-style request bodies into Chat Completions semantics.

Some OpenAI-compatible clients (notably the Cursor IDE agent) reuse a ``/v1``
base URL but POST a Responses-API-shaped body to ``/v1/chat/completions``: the
payload carries ``input`` instead of ``messages``, flat Responses tool
definitions, an ``instructions`` field, a ``reasoning`` object, and
Responses-only fields such as ``user``. ``ChatCompletionsRequest`` requires a
``messages`` array, so those requests fail validation before reaching the
account pool.

This module converts such a body back into the Chat Completions shape so the
existing chat -> responses mapping (``ChatCompletionsRequest.to_responses_request``)
can handle it. The response stays on the Chat Completions contract, which is
what a client posting to ``/chat/completions`` expects.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from typing import cast

from app.core.types import JsonValue
from app.core.utils.json_guards import is_json_list, is_json_mapping

# Scalar fields that carry the same meaning on Chat Completions and can be
# forwarded as-is when present.
_PASSTHROUGH_FIELDS = ("stream", "temperature", "top_p", "parallel_tool_calls", "service_tier")

# Responses content part types that map to plain chat text.
_TEXT_PART_TYPES = frozenset({"input_text", "output_text", "text"})
_IMAGE_PART_TYPES = frozenset({"input_image", "image_url"})


def is_responses_style_chat_body(data: object) -> bool:
    """Return True when ``data`` looks like a Responses body sent to chat.

    The marker is an ``input`` field with no usable ``messages`` array, which is
    exactly what distinguishes a Responses request from a Chat Completions one.
    """

    if not is_json_mapping(data):
        return False
    if "input" not in data:
        return False
    return not data.get("messages")


def responses_style_to_chat_body(data: Mapping[str, JsonValue]) -> dict[str, JsonValue]:
    """Convert a Responses-style body into a Chat Completions body."""

    out: dict[str, JsonValue] = {}

    model = data.get("model")
    if model is not None:
        out["model"] = model

    out["messages"] = _build_messages(data.get("instructions"), data.get("input"))

    tools = _convert_tools(data.get("tools"))
    if tools:
        out["tools"] = tools

    tool_choice = data.get("tool_choice")
    if tool_choice is not None:
        out["tool_choice"] = _convert_tool_choice(tool_choice)

    for field in _PASSTHROUGH_FIELDS:
        value = data.get(field)
        if value is not None:
            out[field] = value

    max_output_tokens = data.get("max_output_tokens")
    if isinstance(max_output_tokens, int) and not isinstance(max_output_tokens, bool):
        out["max_tokens"] = max_output_tokens

    # Forward the whole ``reasoning`` object (effort *and* summary). The upstream
    # only streams reasoning ("thinking") summaries when ``summary`` is requested,
    # so mapping effort alone would silently disable thinking.
    reasoning = data.get("reasoning")
    if is_json_mapping(reasoning):
        out["reasoning"] = dict(reasoning)

    response_format = _text_to_response_format(data.get("text"))
    if response_format is not None:
        out["response_format"] = response_format

    return out


def _build_messages(instructions: JsonValue, input_value: JsonValue) -> list[JsonValue]:
    messages: list[JsonValue] = []
    if isinstance(instructions, str) and instructions:
        messages.append({"role": "system", "content": instructions})

    if isinstance(input_value, str):
        items: list[JsonValue] = [{"role": "user", "content": input_value}]
    elif is_json_list(input_value):
        items = input_value
    else:
        items = []

    pending_tool_calls: list[JsonValue] = []

    def flush_tool_calls() -> None:
        if pending_tool_calls:
            messages.append({"role": "assistant", "tool_calls": list(pending_tool_calls)})
            pending_tool_calls.clear()

    for item in items:
        if isinstance(item, str):
            flush_tool_calls()
            messages.append({"role": "user", "content": item})
            continue
        if not is_json_mapping(item):
            continue

        item_type = item.get("type")
        if item_type == "function_call":
            tool_call = _function_call_to_tool_call(item)
            if tool_call is not None:
                pending_tool_calls.append(tool_call)
            continue

        flush_tool_calls()

        if item_type == "function_call_output":
            tool_message = _function_call_output_to_tool_message(item)
            if tool_message is not None:
                messages.append(tool_message)
            continue
        if item_type in ("reasoning", "item_reference"):
            continue

        role = item.get("role")
        if not isinstance(role, str) or not role:
            continue
        messages.append({"role": role, "content": _convert_content(item.get("content"), role)})

    flush_tool_calls()
    return messages


def _function_call_to_tool_call(item: Mapping[str, JsonValue]) -> JsonValue | None:
    call_id = _first_str(item.get("call_id"), item.get("id"))
    name = item.get("name")
    if call_id is None or not isinstance(name, str) or not name:
        return None
    arguments = item.get("arguments")
    if not isinstance(arguments, str):
        arguments = "{}" if arguments is None else json.dumps(arguments)
    return {
        "id": call_id,
        "type": "function",
        "function": {"name": name, "arguments": arguments},
    }


def _function_call_output_to_tool_message(item: Mapping[str, JsonValue]) -> JsonValue | None:
    call_id = _first_str(item.get("call_id"), item.get("id"))
    if call_id is None:
        return None
    return {"role": "tool", "tool_call_id": call_id, "content": _output_to_text(item.get("output"))}


def _convert_content(content: JsonValue, role: str) -> JsonValue:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if is_json_list(content):
        content_parts: list[JsonValue] = content
    elif is_json_mapping(content):
        content_parts = [cast(JsonValue, content)]
    else:
        return ""

    text_segments: list[str] = []
    parts: list[JsonValue] = []
    has_image = False
    for part in content_parts:
        if isinstance(part, str):
            text_segments.append(part)
            parts.append({"type": "text", "text": part})
            continue
        if not is_json_mapping(part):
            continue
        part_type = part.get("type")
        if part_type in _TEXT_PART_TYPES or part_type is None:
            text = part.get("text")
            if isinstance(text, str):
                text_segments.append(text)
                parts.append({"type": "text", "text": text})
        elif part_type == "refusal":
            text = part.get("refusal")
            if isinstance(text, str):
                text_segments.append(text)
                parts.append({"type": "text", "text": text})
        elif part_type in _IMAGE_PART_TYPES:
            url = _image_url(part.get("image_url"))
            if url is not None:
                has_image = True
                parts.append({"type": "image_url", "image_url": {"url": url}})

    # Only ``user`` messages may carry image parts on Chat Completions; for every
    # other role (and text-only user messages) collapse to a plain string, which
    # also keeps ``system``/``developer`` messages text-only.
    if role == "user" and has_image:
        return parts
    return "".join(text_segments)


def _convert_tools(tools: JsonValue) -> list[JsonValue]:
    if not is_json_list(tools):
        return []
    converted: list[JsonValue] = []
    for tool in tools:
        if not is_json_mapping(tool):
            continue
        if is_json_mapping(tool.get("function")):
            converted.append(tool)
            continue
        tool_type = tool.get("type")
        if tool_type == "function":
            function = {key: tool[key] for key in ("name", "description", "parameters", "strict") if key in tool}
            converted.append({"type": "function", "function": function})
        elif tool_type in ("web_search", "web_search_preview"):
            converted.append(tool)
        # Other built-in Responses tool types have no Chat Completions mapping
        # and are dropped rather than forwarded as invalid entries.
    return converted


def _convert_tool_choice(tool_choice: JsonValue) -> JsonValue:
    if not is_json_mapping(tool_choice):
        return tool_choice
    if tool_choice.get("type") == "function":
        name = tool_choice.get("name")
        if isinstance(name, str) and name:
            return {"type": "function", "function": {"name": name}}
    return tool_choice


def _text_to_response_format(text: JsonValue) -> JsonValue | None:
    if not is_json_mapping(text):
        return None
    fmt = text.get("format")
    if not is_json_mapping(fmt):
        return None
    fmt_type = fmt.get("type")
    if fmt_type in ("json_object", "text"):
        return {"type": fmt_type}
    if fmt_type == "json_schema":
        json_schema = {key: fmt[key] for key in ("name", "schema", "strict") if key in fmt}
        return {"type": "json_schema", "json_schema": json_schema}
    return None


def _image_url(image_url: JsonValue) -> str | None:
    if isinstance(image_url, str) and image_url:
        return image_url
    if is_json_mapping(image_url):
        url = image_url.get("url")
        if isinstance(url, str) and url:
            return url
    return None


def _output_to_text(output: JsonValue) -> str:
    if isinstance(output, str):
        return output
    if is_json_list(output):
        segments: list[str] = []
        for part in output:
            if isinstance(part, str):
                segments.append(part)
            elif is_json_mapping(part):
                text = part.get("text")
                if isinstance(text, str):
                    segments.append(text)
        if segments:
            return "".join(segments)
    if output is None:
        return ""
    return json.dumps(output)


def _first_str(*values: JsonValue) -> str | None:
    for value in values:
        if isinstance(value, str) and value:
            return value
    return None
