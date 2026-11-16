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
      className={`rounded-[8px] border border-risk-line bg-risk-soft p-3 ${className}`}
      role="alert"
    >
      <div className="flex items-start gap-3">
        <AlertCircle className="w-4 h-4 text-risk mt-0.5 shrink-0" />
        <div className="flex-1 min-w-0">
          <p className="text-[13px] text-fg">{message}</p>
        </div>
        {onDismiss && !hasActions && (
          <button
            onClick={onDismiss}
            className="shrink-0 p-1 text-fg-3 hover:text-fg rounded-md transition-colors"
            aria-label="Dismiss error"
          >
            <X className="w-4 h-4" />
          </button>
        )}
      </div>

      {hasActions && (
        <div className="mt-3 flex gap-2">
          {showRetry && onRetry && (
            <button onClick={onRetry} className="btn btn-secondary btn-sm">
              <RefreshCw className="w-3.5 h-3.5" />
              Try Again
            </button>
          )}
          {onDismiss && (
            <button onClick={onDismiss} className="btn btn-ghost btn-sm">
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
    <div className={`flex items-center gap-2 text-[13px] text-risk ${className}`} role="alert">
      <AlertCircle className="w-4 h-4 shrink-0" />
      <span>{message}</span>
    </div>
  );
}
