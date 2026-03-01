"""ConnectRPC status codes.

Standard gRPC/Connect status codes as defined in:
https://grpc.github.io/grpc/core/md_doc_statuscodes.html
"""

from enum import IntEnum


class Code(IntEnum):
    """ConnectRPC/gRPC status codes."""

    def __str__(self) -> str:
        """Return the code name for string representation."""
        return self.name

    # Success
    OK = 0

    # The operation was cancelled (typically by the caller).
    CANCELED = 1
    CANCELLED = 1  # Alias for British spelling

    # Unknown error.
    UNKNOWN = 2

    # Client specified an invalid argument.
    INVALID_ARGUMENT = 3

    # Deadline expired before operation could complete.
    DEADLINE_EXCEEDED = 4

    # Requested entity was not found.
    NOT_FOUND = 5

    # Attempt to create an entity that already exists.
    ALREADY_EXISTS = 6

    # Caller does not have permission for this operation.
    PERMISSION_DENIED = 7

    # Resource has been exhausted.
    RESOURCE_EXHAUSTED = 8

    # Operation was rejected because the system state
    # required for the operation doesn't exist.
    FAILED_PRECONDITION = 9

    # Operation was aborted.
    ABORTED = 10

    # Operation was attempted past the valid range.
    OUT_OF_RANGE = 11

    # Operation is not implemented or supported.
    UNIMPLEMENTED = 12

    # Internal errors.
    INTERNAL = 13

    # The service is currently unavailable.
    UNAVAILABLE = 14

    # Unrecoverable data loss or corruption.
    DATA_LOSS = 15

    # The request does not have valid authentication credentials.
    UNAUTHENTICATED = 16
