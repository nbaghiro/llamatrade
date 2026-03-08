/**
 * Reusable error alert component with retry and dismiss actions.
 *
 * Displays user-friendly error messages in a consistent format across the app.
 */

import { AlertCircle, RefreshCw, X } from 'lucide-react';

interface ErrorAlertProps {
  /** The error message to display */
  message: string;
  /** Callback when retry button is clicked */
  onRetry?: () => void;
  /** Callback when dismiss button is clicked */
  onDismiss?: () => void;
  /** Whether to show the retry button (default: true if onRetry provided) */
  showRetry?: boolean;
  /** Custom class name for the container */
  className?: string;
}

export function ErrorAlert({
  message,
  onRetry,
  onDismiss,
  showRetry = true,
  className = '',
}: ErrorAlertProps) {
  const hasActions = (showRetry && onRetry) || onDismiss;

  return (
    <div
      className={`rounded-lg border border-red-200 bg-red-50 dark:bg-red-900/20 dark:border-red-800 p-4 ${className}`}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="w-5 h-5 text-red-600 dark:text-red-400 mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-sm text-red-700 dark:text-red-300">{message}</p>
        </div>
        {onDismiss && !hasActions && (
          <button
            onClick={onDismiss}
            className="shrink-0 p-1 text-red-500 hover:text-red-700 dark:text-red-400 dark:hover:text-red-300 rounded-md hover:bg-red-100 dark:hover:bg-red-900/40 transition-colors"
            aria-label="Dismiss error"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {hasActions && (
        <div className="mt-3 flex gap-2">
          {showRetry && onRetry && (
            <button
              onClick={onRetry}
              className="inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-md text-red-700 bg-red-100 hover:bg-red-200 dark:text-red-200 dark:bg-red-900/40 dark:hover:bg-red-900/60 transition-colors"
            >
              <RefreshCw className="w-3.5 h-3.5 mr-1.5" />
              Try Again
            </button>
          )}
          {onDismiss && (
            <button
              onClick={onDismiss}
              className="inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-md text-red-600 hover:text-red-700 hover:bg-red-100 dark:text-red-300 dark:hover:text-red-200 dark:hover:bg-red-900/40 transition-colors"
            >
              Dismiss
            </button>
          )}
        </div>
      )}
    </div>
  );
}

/**
 * Inline error alert for displaying errors within forms or smaller contexts.
 */
interface InlineErrorProps {
  message: string;
  className?: string;
}

export function InlineError({ message, className = '' }: InlineErrorProps) {
  return (
    <div
      className={`flex items-center gap-2 text-sm text-red-600 dark:text-red-400 ${className}`}
      role="alert"
    >
      <AlertCircle className="w-4 h-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}
