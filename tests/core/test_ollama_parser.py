"""Tests for ChatStreamParser (axiom.core.ollama)."""

from __future__ import annotations

import json

import pytest

from axiom.core.errors import InvalidResponseError
from axiom.core.ollama import ChatStreamParser


def line(payload: dict) -> str:
    return json.dumps(payload)


def test_empty_and_blank_lines_yield_empty_chunk():
    parser = ChatStreamParser()
    assert parser.feed_line("").content == ""
    assert parser.feed_line("   ").thinking == ""
    assert parser.feed_line("   ").done is False


def test_malformed_json_raises_invalid_response():
    parser = ChatStreamParser()
    with pytest.raises(InvalidResponseError):
        parser.feed_line("{not json")


def test_non_object_json_raises():
    parser = ChatStreamParser()
    with pytest.raises(InvalidResponseError):
        parser.feed_line("[1, 2, 3]")


def test_error_payload_raises():
    parser = ChatStreamParser()
    with pytest.raises(InvalidResponseError):
        parser.feed_line(line({"error": "model not found"}))


def test_native_thinking_and_content_split():
    parser = ChatStreamParser()
    chunk = parser.feed_line(
        line(
            {
                "message": {
                    "role": "assistant",
                    "thinking": "let me think",
                    "content": "hello",
                }
            }
        )
    )
    assert chunk.thinking == "let me think"
    assert chunk.content == "hello"
    assert chunk.done is False


def test_content_only_model_has_no_thinking():
    parser = ChatStreamParser()
    chunk = parser.feed_line(
        line({"message": {"role": "assistant", "content": "final answer"}})
    )
    assert chunk.content == "final answer"
    assert chunk.thinking == ""


def test_legacy_think_tags_separated_from_content():
    parser = ChatStreamParser()
    chunk = parser.feed_line(
        line(
            {
                "message": {
                    "role": "assistant",
                    "content": "before <think>inner</think> after",
                }
            }
        )
    )
    assert chunk.content == "before  after"
    assert chunk.thinking == "inner"


def test_legacy_think_split_across_chunks():
    parser = ChatStreamParser()
    first = parser.feed_line(
        line({"message": {"role": "assistant", "content": "answer <thi"}})
    )
    second = parser.feed_line(
        line({"message": {"role": "assistant", "content": "nk>split</think> tail"}})
    )
    content = first.content + second.content
    thinking = first.thinking + second.thinking
    assert thinking == "split"
    assert "answer" in content and "tail" in content
    assert "split" not in content


def test_unclosed_legacy_think_flushed_as_thinking():
    parser = ChatStreamParser()
    chunk = parser.feed_line(
        line({"message": {"role": "assistant", "content": "text <think>never closed"}})
    )
    # Unclosed reasoning streams immediately as thinking (never as content);
    # flush must not resurrect it as content.
    assert "never closed" in chunk.thinking
    assert "never closed" not in chunk.content
    tail = parser.flush()
    assert "never closed" not in tail.content


def test_tool_calls_with_dict_arguments():
    parser = ChatStreamParser()
    chunk = parser.feed_line(
        line(
            {
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "web_search",
                                "arguments": {"query": "news"},
                            }
                        }
                    ],
                }
            }
        )
    )
    assert len(chunk.tool_calls) == 1
    assert chunk.tool_calls[0].name == "web_search"
    assert chunk.tool_calls[0].arguments == {"query": "news"}


def test_tool_calls_with_json_string_arguments():
    parser = ChatStreamParser()
    chunk = parser.feed_line(
        line(
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "function": {
                                "name": "web_search",
                                "arguments": '{"query": "x"}',
                            }
                        }
                    ],
                }
            }
        )
    )
    assert chunk.tool_calls[0].arguments == {"query": "x"}


def test_tool_call_without_name_is_skipped():
    parser = ChatStreamParser()
    chunk = parser.feed_line(
        line(
            {
                "message": {
                    "content": "hi",
                    "tool_calls": [{"function": {"arguments": {}}}],
                }
            }
        )
    )
    assert chunk.tool_calls == []
    assert chunk.content == "hi"


def test_final_metadata_chunk():
    parser = ChatStreamParser()
    chunk = parser.feed_line(
        line(
            {
                "done": True,
                "done_reason": "stop",
                "total_duration": 100,
                "eval_count": 12,
                "message": {"role": "assistant", "content": ""},
            }
        )
    )
    assert chunk.done is True
    assert chunk.done_reason == "stop"
    assert chunk.metrics["eval_count"] == 12
    assert chunk.content == ""


def test_unexpected_fields_ignored_and_flush_empty():
    parser = ChatStreamParser()
    chunk = parser.feed_line(
        line({"message": {"content": "ok", "future": {"a": 1}}, "weird_top": [1]})
    )
    assert chunk.content == "ok"
    assert parser.flush().content == ""
