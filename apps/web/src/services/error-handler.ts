/**
 * Centralized error handling for frontend services.
 *
 * Transforms technical errors (ConnectError, network errors, etc.) into
 * user-friendly messages for display in the UI.
 */

import { Code, ConnectError } from '@connectrpc/connect';

/**
 * Standardized error representation for UI display.
 */
export interface AppError {
  /** User-friendly error message */
  message: string;
  /** Error code for logging/debugging */
  code: string;
  /** Whether the operation can be retried */
  isRetryable: boolean;
  /** Whether this is an authentication error requiring login */
  isAuthError: boolean;
}

/**
 * Transform any error into a user-friendly AppError.
 *
 * @param error - The error to transform
 * @returns A standardized AppError for UI display
 */
export function transformError(error: unknown): AppError {
  if (error instanceof ConnectError) {
    return transformConnectError(error);
  }

  if (error instanceof Error) {
    // Network errors
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      return {
        message: 'Unable to connect to the server. Please check your connection.',
        code: 'NETWORK_ERROR',
        isRetryable: true,
        isAuthError: false,
      };
    }

    // Timeout errors
    if (error.name === 'TimeoutError' || error.message.includes('timeout')) {
      return {
        message: 'The request timed out. Please try again.',
        code: 'TIMEOUT',
        isRetryable: true,
        isAuthError: false,
      };
    }

    return {
      message: 'An unexpected error occurred. Please try again.',
      code: 'UNKNOWN_ERROR',
      isRetryable: true,
      isAuthError: false,
    };
  }

  return {
    message: 'Something went wrong',
    code: 'UNKNOWN',
    isRetryable: true,
    isAuthError: false,
  };
}

/**
 * Transform a ConnectError into a user-friendly AppError.
 */
function transformConnectError(error: ConnectError): AppError {
  switch (error.code) {
    case Code.NotFound:
      return {
        message: 'The requested item was not found',
        code: 'NOT_FOUND',
        isRetryable: false,
        isAuthError: false,
      };

    case Code.InvalidArgument:
      return {
        message: extractValidationMessage(error),
        code: 'INVALID_INPUT',
        isRetryable: false,
        isAuthError: false,
      };

    case Code.FailedPrecondition:
      return {
        message: extractPreconditionMessage(error),
        code: 'PRECONDITION_FAILED',
        isRetryable: false,
        isAuthError: false,
      };

    case Code.Unauthenticated:
      return {
        message: 'Please log in to continue',
        code: 'AUTH_REQUIRED',
        isRetryable: false,
        isAuthError: true,
      };

    case Code.PermissionDenied:
      return {
        message: "You don't have permission to perform this action",
        code: 'FORBIDDEN',
        isRetryable: false,
        isAuthError: false,
      };

    case Code.Unavailable:
      return {
        message: 'Service temporarily unavailable. Please try again.',
        code: 'SERVICE_DOWN',
        isRetryable: true,
        isAuthError: false,
      };

    case Code.Internal:
      return {
        message: 'An internal error occurred. Please try again.',
        code: 'INTERNAL',
        isRetryable: true,
        isAuthError: false,
      };

    case Code.DeadlineExceeded:
      return {
        message: 'The request took too long. Please try again.',
        code: 'TIMEOUT',
        isRetryable: true,
        isAuthError: false,
      };

    case Code.ResourceExhausted:
      return {
        message: 'Too many requests. Please wait a moment and try again.',
        code: 'RATE_LIMITED',
        isRetryable: true,
        isAuthError: false,
      };

    default:
      return {
        message: 'An error occurred. Please try again.',
        code: 'UNKNOWN',
        isRetryable: true,
        isAuthError: false,
      };
  }
}

/**
 * Extract a user-friendly validation message from an InvalidArgument error.
 */
function extractValidationMessage(error: ConnectError): string {
  const msg = error.message;

  // Clean up common validation message patterns
  if (msg.includes('Invalid strategy:')) {
    return msg.replace('Invalid strategy:', 'Strategy error:').trim();
  }

  if (msg.includes('must be a valid UUID')) {
    return 'Invalid identifier format';
  }

  // If the message is already clean and short, use it
  if (msg.length < 100 && !msg.includes('\n')) {
    return msg || 'Invalid input provided';
  }

  return 'Invalid input provided';
}

/**
 * Extract a user-friendly message from a FailedPrecondition error.
 */
function extractPreconditionMessage(error: ConnectError): string {
  const msg = error.message;

  if (msg.includes('constraint violation')) {
    return 'This operation conflicts with existing data';
  }

  if (msg.includes('already exists')) {
    return 'An item with this name already exists';
  }

  // If the message is clean and short, use it
  if (msg.length < 100 && !msg.includes('\n')) {
    return msg || 'This operation cannot be performed';
  }

  return 'This operation cannot be performed';
}

/**
 * Log an error with context for debugging.
 */
export function logError(error: unknown, context: string): void {
  /* eslint-disable no-console */
  if (error instanceof ConnectError) {
    console.error(`[${context}] ConnectError (${Code[error.code]}):`, error.message);
  } else if (error instanceof Error) {
    console.error(`[${context}] Error:`, error.message);
  } else {
    console.error(`[${context}] Unknown error:`, error);
  }
  /* eslint-enable no-console */
}
