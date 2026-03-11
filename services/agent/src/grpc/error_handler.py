"""Error handling utilities for Connect servicer.

Catches service exceptions and transforms them into user-friendly
ConnectError responses.
"""

from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine
from functools import wraps
from typing import Any
from uuid import UUID

from connectrpc.code import Code
from connectrpc.errors import ConnectError
from sqlalchemy.exc import IntegrityError, OperationalError, SQLAlchemyError

logger = logging.getLogger(__name__)


def parse_uuid(value: str, field_name: str) -> UUID:
    """Parse a UUID string, raising ConnectError on failure.

    Args:
        value: The string to parse as UUID
        field_name: Name of the field for error messages

    Returns:
        The parsed UUID

    Raises:
        ConnectError: If the string is not a valid UUID
    """
    if not value:
        raise ConnectError(Code.INVALID_ARGUMENT, f"{field_name} is required")
    try:
        return UUID(value)
    except ValueError:
        raise ConnectError(
            Code.INVALID_ARGUMENT,
            f"Invalid {field_name}: must be a valid UUID",
        )


def handle_service_errors[**P, T](
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, T]]:
    """Decorator to handle common service errors and convert to ConnectError.

    Transforms technical errors into user-friendly ConnectError responses:
    - ConnectError: Re-raised as-is (already user-friendly)
    - IntegrityError: "Data constraint violation"
    - OperationalError: "Database temporarily unavailable"
    - SQLAlchemyError: "An internal error occurred"
    - ValueError: Passed through as INVALID_ARGUMENT
    - Other exceptions: "An unexpected error occurred" (logged with details)
    """

    @wraps(func)
    async def wrapper(*args: P.args, **kwargs: P.kwargs) -> T:
        try:
            return await func(*args, **kwargs)
        except ConnectError:
            # Already a user-friendly error, re-raise
            raise
        except IntegrityError as e:
            logger.warning(f"Integrity error in {func.__name__}: {e}")
            raise ConnectError(
                Code.FAILED_PRECONDITION,
                "Data constraint violation. The operation conflicts with existing data.",
            )
        except OperationalError as e:
            logger.error(f"Database operational error in {func.__name__}: {e}")
            raise ConnectError(
                Code.UNAVAILABLE,
                "Database temporarily unavailable. Please try again.",
            )
        except SQLAlchemyError as e:
            logger.error(f"Database error in {func.__name__}: {e}")
            raise ConnectError(
                Code.INTERNAL,
                "An internal database error occurred. Please try again.",
            )
        except ValueError as e:
            # Validation errors are invalid arguments
            raise ConnectError(Code.INVALID_ARGUMENT, str(e))
        except Exception as e:
            logger.exception(f"Unexpected error in {func.__name__}: {e}")
            raise ConnectError(
                Code.INTERNAL,
                "An unexpected error occurred. Please try again.",
            )

    return wrapper
