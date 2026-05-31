from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.openai.chat_requests import ChatCompletionsRequest
from app.core.openai.responses_style_chat import (
    is_responses_style_chat_body,
    responses_style_to_chat_body,
)


def test_detects_responses_style_body():
    assert is_responses_style_chat_body({"model": "gpt-5.5", "input": "hi"}) is True


def test_messages_body_is_not_responses_style():
    body = {"model": "gpt-5.5", "messages": [{"role": "user", "content": "hi"}], "input": "ignored"}
    assert is_responses_style_chat_body(body) is False


def test_string_input_becomes_user_message_and_drops_unsupported_fields():
    body = {"model": "gpt-5.5", "input": "hello", "user": "abc", "store": True}
    chat = responses_style_to_chat_body(body)
    assert chat["messages"] == [{"role": "user", "content": "hello"}]
    assert "user" not in chat
    assert "store" not in chat


def test_instructions_become_leading_system_message():
    body = {"model": "gpt-5.5", "instructions": "be terse", "input": [{"role": "user", "content": "hi"}]}
    chat = responses_style_to_chat_body(body)
    assert chat["messages"][0] == {"role": "system", "content": "be terse"}
    assert chat["messages"][1] == {"role": "user", "content": "hi"}


def test_responses_content_parts_flatten_to_text():
    body = {
        "model": "gpt-5.5",
        "input": [{"role": "system", "content": [{"type": "input_text", "text": "you are gpt"}]}],
    }
    chat = responses_style_to_chat_body(body)
    assert chat["messages"] == [{"role": "system", "content": "you are gpt"}]


def test_flat_function_tool_normalized_to_nested():
    body = {
        "model": "gpt-5.5",
        "input": "hi",
        "tools": [{"type": "function", "name": "do_it", "description": "d", "parameters": {"type": "object"}}],
    }
    chat = responses_style_to_chat_body(body)
    assert chat["tools"] == [
        {"type": "function", "function": {"name": "do_it", "description": "d", "parameters": {"type": "object"}}}
    ]


def test_already_nested_tool_is_preserved():
    tool = {"type": "function", "function": {"name": "x", "parameters": {}}}
    chat = responses_style_to_chat_body({"model": "gpt-5.5", "input": "hi", "tools": [tool]})
    assert chat["tools"] == [tool]


def test_reasoning_object_forwarded_and_max_output_tokens_mapped():
    body = {
        "model": "gpt-5.5",
        "input": "hi",
        "reasoning": {"effort": "high", "summary": "auto"},
        "max_output_tokens": 256,
    }
    chat = responses_style_to_chat_body(body)
    # The whole reasoning object (incl. ``summary``) must survive so the upstream
    # streams reasoning summaries.
    assert chat["reasoning"] == {"effort": "high", "summary": "auto"}
    assert chat["max_tokens"] == 256
    responses = ChatCompletionsRequest.model_validate(body).to_responses_request()
    assert responses.reasoning is not None


def test_text_format_mapped_to_response_format():
    body = {"model": "gpt-5.5", "input": "hi", "text": {"format": {"type": "json_object"}}}
    chat = responses_style_to_chat_body(body)
    assert chat["response_format"] == {"type": "json_object"}


def test_user_image_part_is_preserved_as_list():
    body = {
        "model": "gpt-5.5",
        "input": [
            {
                "role": "user",
                "content": [
                    {"type": "input_text", "text": "look"},
                    {"type": "input_image", "image_url": "https://example.com/a.png"},
                ],
            }
        ],
    }
    chat = responses_style_to_chat_body(body)
    assert chat["messages"][0]["content"] == [
        {"type": "text", "text": "look"},
        {"type": "image_url", "image_url": {"url": "https://example.com/a.png"}},
    ]


def test_function_call_round_trip_to_responses_items():
    body = {
        "model": "gpt-5.5",
        "input": [
            {"role": "user", "content": "run it"},
            {"type": "function_call", "call_id": "call_42", "name": "do_it", "arguments": '{"x":1}'},
            {"type": "function_call_output", "call_id": "call_42", "output": "done"},
        ],
        "tools": [{"type": "function", "name": "do_it", "parameters": {"type": "object"}}],
    }
    chat = responses_style_to_chat_body(body)
    assert chat["messages"][1] == {
        "role": "assistant",
        "tool_calls": [{"id": "call_42", "type": "function", "function": {"name": "do_it", "arguments": '{"x":1}'}}],
    }
    assert chat["messages"][2] == {"role": "tool", "tool_call_id": "call_42", "content": "done"}

    # End-to-end: the normalized request maps to Responses function-call items.
    responses = ChatCompletionsRequest.model_validate(body).to_responses_request()
    item_types = [item.get("type") for item in responses.input if isinstance(item, dict)]
    assert "function_call" in item_types
    assert "function_call_output" in item_types


def test_reasoning_items_are_dropped():
    body = {
        "model": "gpt-5.5",
        "input": [
            {"type": "reasoning", "summary": []},
            {"role": "user", "content": "hi"},
        ],
    }
    chat = responses_style_to_chat_body(body)
    assert chat["messages"] == [{"role": "user", "content": "hi"}]


def test_request_model_accepts_responses_style_body():
    body = {"model": "gpt-5.5", "input": "hi", "user": "abc", "stream": True}
    req = ChatCompletionsRequest.model_validate(body)
    assert req.stream is True
    responses = req.to_responses_request()
    assert responses.model == "gpt-5.5"
    assert responses.input == [{"role": "user", "content": [{"type": "input_text", "text": "hi"}]}]


def test_empty_input_normalizes_to_invalid_request():
    with pytest.raises(ValidationError):
        ChatCompletionsRequest.model_validate({"model": "gpt-5.5", "input": []})
