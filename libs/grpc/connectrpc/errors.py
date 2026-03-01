"""ConnectRPC error types.

Provides ConnectError exception class compatible with the Connect protocol.
"""

from __future__ import annotations

from typing import Any

from connectrpc.code import Code


class ConnectError(Exception):
    """Exception representing a Connect protocol error.

    ConnectError is raised by services to indicate an error condition
    that should be returned to the client with a specific status code.

    Attributes:
        code: The Connect/gRPC status code.
        message: Human-readable error message.
        details: Optional additional error details.

    Example:
        raise ConnectError(Code.NOT_FOUND, "User not found")
        raise ConnectError(Code.INVALID_ARGUMENT, "Invalid email format")
    """

    def __init__(
        self,
        code: Code | int,
        message: str = "",
        details: list[Any] | None = None,
    ) -> None:
        """Initialize a ConnectError.

        Args:
            code: The status code (Code enum or int).
            message: Human-readable error message.
            details: Optional list of additional error details.
        """
        super().__init__(message)
        self._code = Code(code) if isinstance(code, int) else code
        self._message = message
        self._details = details or []

    @property
    def code(self) -> Code:
        """Get the status code."""
        return self._code

    @property
    def message(self) -> str:
        """Get the error message."""
        return self._message

    @property
    def details(self) -> list[Any]:
        """Get error details."""
        return self._details

    def __str__(self) -> str:
        """Return string representation."""
        return f"[{self._code.name}] {self._message}"

    def __repr__(self) -> str:
        """Return detailed representation."""
        return f"ConnectError(code={self._code!r}, message={self._message!r})"
