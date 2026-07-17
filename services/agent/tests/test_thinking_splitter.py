"""Tests for the streaming <thinking> splitter."""

from __future__ import annotations

from src.llm.thinking import CONTENT, THINKING, ThinkingSplitter


def _run(chunks: list[str]) -> tuple[str, str]:
    """Feed chunks through a splitter and return (thinking, content) joined."""
    splitter = ThinkingSplitter()
    segments: list[tuple[str, str]] = []
    for chunk in chunks:
        segments.extend(splitter.feed(chunk))
    segments.extend(splitter.flush())
    thinking = "".join(t for ch, t in segments if ch == THINKING)
    content = "".join(t for ch, t in segments if ch == CONTENT)
    return thinking, content


def test_no_tags_is_all_content() -> None:
    """When the model omits tags, every char is content (graceful fallback)."""
    thinking, content = _run(["Hello ", "world"])
    assert thinking == ""
    assert content == "Hello world"


def test_single_chunk_thinking_then_answer() -> None:
    thinking, content = _run(["<thinking>weighing options</thinking>Here is the answer"])
    assert thinking == "weighing options"
    assert content == "Here is the answer"


def test_tag_split_across_deltas() -> None:
    """An open tag straddling two deltas must not leak as literal text."""
    thinking, content = _run(["<thin", "king>reasoning</think", "ing>answer"])
    assert thinking == "reasoning"
    assert content == "answer"


def test_close_tag_split_across_deltas() -> None:
    thinking, content = _run(["<thinking>abc", "</thinking", ">xyz"])
    assert thinking == "abc"
    assert content == "xyz"


def test_char_by_char_streaming() -> None:
    """Degenerate one-char-at-a-time streaming still routes correctly."""
    full = "<thinking>hmm</thinking>done"
    thinking, content = _run(list(full))
    assert thinking == "hmm"
    assert content == "done"


def test_content_before_open_tag_is_preserved() -> None:
    """Any text before <thinking> stays content (tag need not be first)."""
    thinking, content = _run(["prefix <thinking>mid</thinking> suffix"])
    assert thinking == "mid"
    assert content == "prefix  suffix"


def test_unterminated_thinking_flushes_as_thinking() -> None:
    """A never-closed <thinking> emits its remainder rather than swallowing it."""
    thinking, content = _run(["<thinking>still going"])
    assert thinking == "still going"
    assert content == ""


def test_dangling_partial_open_tag_flushes_as_literal() -> None:
    """A trailing '<thin' that never completes is emitted as literal content."""
    thinking, content = _run(["answer<thin"])
    assert thinking == ""
    assert content == "answer<thin"


def test_lone_left_angle_is_not_held_forever() -> None:
    thinking, content = _run(["a < b"])
    assert thinking == ""
    assert content == "a < b"


def test_multiple_thinking_blocks() -> None:
    thinking, content = _run(["<thinking>one</thinking>A<thinking>two</thinking>B"])
    assert thinking == "onetwo"
    assert content == "AB"


def test_empty_thinking_block() -> None:
    thinking, content = _run(["<thinking></thinking>answer"])
    assert thinking == ""
    assert content == "answer"
