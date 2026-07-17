"""Split a streamed LLM response into curated <thinking> reasoning vs. answer text.

The model is prompted to prefix its answer with a short reasoning note wrapped in
``<thinking>...</thinking>``. This streaming splitter routes text deltas to two
channels — "thinking" and "content" — coping with tags that straddle delta
boundaries and degrading gracefully (all text is "content") when the model omits
the tags entirely.
"""

from __future__ import annotations

OPEN_TAG = "<thinking>"
CLOSE_TAG = "</thinking>"

THINKING = "thinking"
CONTENT = "content"


def _partial_tag_suffix(buf: str, tag: str) -> int:
    """Length of the longest buf-suffix that is a proper prefix of tag (else 0).

    Held back between deltas so a tag split across a boundary (e.g. ``"<thi"`` then
    ``"nking>"``) is not mis-emitted as literal text.
    """
    for k in range(min(len(buf), len(tag) - 1), 0, -1):
        if buf[-k:] == tag[:k]:
            return k
    return 0


class ThinkingSplitter:
    """Incrementally route streamed text into ordered (channel, text) segments."""

    def __init__(self) -> None:
        self._buffer = ""
        self._in_thinking = False

    def feed(self, text: str) -> list[tuple[str, str]]:
        """Consume a text delta, returning ordered (channel, text) segments."""
        if text:
            self._buffer += text
        return self._drain(final=False)

    def flush(self) -> list[tuple[str, str]]:
        """Emit any buffered remainder at end-of-stream (an unterminated tag is literal)."""
        return self._drain(final=True)

    def _drain(self, *, final: bool) -> list[tuple[str, str]]:
        segments: list[tuple[str, str]] = []
        while self._buffer:
            if self._in_thinking:
                tag, channel, next_state = CLOSE_TAG, THINKING, False
            else:
                tag, channel, next_state = OPEN_TAG, CONTENT, True

            idx = self._buffer.find(tag)
            if idx != -1:
                if idx > 0:
                    segments.append((channel, self._buffer[:idx]))
                self._buffer = self._buffer[idx + len(tag) :]
                self._in_thinking = next_state
                continue

            # Tag absent: emit everything except a possible partial tag suffix, which
            # is held for the next delta (unless this is the final flush).
            hold = 0 if final else _partial_tag_suffix(self._buffer, tag)
            emit = self._buffer[: len(self._buffer) - hold]
            if emit:
                segments.append((channel, emit))
            self._buffer = self._buffer[len(self._buffer) - hold :]
            break

        return segments
