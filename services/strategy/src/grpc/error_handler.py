"""Error handling decorator for gRPC service methods.

Catches database and service exceptions and transforms them into user-friendly
ConnectError responses, preventing raw technical details from reaching the UI.
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


def handle_service_errors[**P, T](
    func: Callable[P, Coroutine[Any, Any, T]],
) -> Callable[P, Coroutine[Any, Any, T]]:
    """Decorator to catch and transform database/service errors.

    Transforms technical errors into user-friendly ConnectError responses:
    - ConnectError: Re-raised as-is (already user-friendly)
    - IntegrityError: "Data constraint violation"
    - OperationalError: "Database temporarily unavailable"
    - SQLAlchemyError: "An internal error occurred"
    - ValueError: Passed through with message (validation errors)
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
        # Note: ValueError is NOT caught here - methods should handle it explicitly
        # with the appropriate error code (INVALID_ARGUMENT or FAILED_PRECONDITION)
        except Exception as e:
            logger.exception(f"Unexpected error in {func.__name__}: {e}")
            raise ConnectError(
                Code.INTERNAL,
                "An unexpected error occurred. Please try again.",
            )

    return wrapper


def parse_uuid(uuid_str: str, field_name: str = "id") -> UUID:
    """Parse UUID string with proper error handling.

    Args:
        uuid_str: The UUID string to parse
        field_name: Name of the field for error messages (e.g., "strategy_id")

    Returns:
        Parsed UUID

    Raises:
        ConnectError: If the string is not a valid UUID
    """
    try:
        return UUID(uuid_str)
    except ValueError:
        raise ConnectError(
            Code.INVALID_ARGUMENT,
            f"Invalid {field_name}: must be a valid UUID",
        )
