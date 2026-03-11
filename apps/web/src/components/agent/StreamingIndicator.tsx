/**
 * Streaming indicator component.
 *
 * Shows a typing animation while the assistant is generating a response.
 */

import { Bot } from 'lucide-react';

interface StreamingIndicatorProps {
  content?: string;
}

export function StreamingIndicator({ content }: StreamingIndicatorProps) {
  return (
    <div className="flex gap-3">
      {/* Avatar */}
      <div className="flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400">
        <Bot className="w-4 h-4" />
      </div>

      {/* Message bubble */}
      <div className="flex-1 max-w-[80%] rounded-lg px-4 py-2 bg-gray-100 dark:bg-gray-800">
        {content ? (
          <div className="text-sm text-gray-900 dark:text-gray-100 whitespace-pre-wrap">
            {content}
            <span className="inline-block w-2 h-4 ml-0.5 bg-purple-500 animate-pulse" />
          </div>
        ) : (
          <div className="flex items-center gap-1 py-1">
            <span className="w-2 h-2 rounded-full bg-purple-500 animate-bounce" style={{ animationDelay: '0ms' }} />
            <span className="w-2 h-2 rounded-full bg-purple-500 animate-bounce" style={{ animationDelay: '150ms' }} />
            <span className="w-2 h-2 rounded-full bg-purple-500 animate-bounce" style={{ animationDelay: '300ms' }} />
          </div>
        )}
      </div>
    </div>
  );
}
