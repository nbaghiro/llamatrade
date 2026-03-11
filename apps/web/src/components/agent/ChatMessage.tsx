/**
 * Chat message bubble component.
 *
 * Renders user and assistant messages with appropriate styling.
 * Supports markdown rendering for assistant messages.
 * Supports inline artifact rendering for strategy visualizations.
 */

import { Bot, User } from 'lucide-react';
import { useMemo } from 'react';

import { AgentMessage, ArtifactType, MessageRole, type PendingArtifact } from '../../store/agent';

import { InlineStrategyViewer } from './InlineStrategyViewer';

interface ChatMessageProps {
  message: AgentMessage;
  /** Map of artifact ID to artifact data for inline rendering */
  artifacts?: Map<string, PendingArtifact>;
}

export function ChatMessage({ message, artifacts }: ChatMessageProps) {
  const isUser = message.role === MessageRole.USER;

  // Get linked artifacts for this message (only for assistant messages)
  const linkedArtifacts = useMemo(() => {
    if (isUser || !message.inlineArtifactIds?.length || !artifacts) {
      return [];
    }
    return message.inlineArtifactIds
      .map((id) => artifacts.get(id))
      .filter((a): a is PendingArtifact => a !== undefined);
  }, [isUser, message.inlineArtifactIds, artifacts]);

  return (
    <div className={`flex gap-3 ${isUser ? 'flex-row-reverse' : ''}`}>
      {/* Avatar */}
      <div
        className={`flex-shrink-0 w-8 h-8 rounded-full flex items-center justify-center ${
          isUser
            ? 'bg-blue-100 dark:bg-blue-900/30 text-blue-600 dark:text-blue-400'
            : 'bg-purple-100 dark:bg-purple-900/30 text-purple-600 dark:text-purple-400'
        }`}
      >
        {isUser ? <User className="w-4 h-4" /> : <Bot className="w-4 h-4" />}
      </div>

      {/* Message content */}
      <div className={`flex-1 max-w-[80%] ${isUser ? 'ml-auto' : ''}`}>
        {/* Text bubble */}
        <div
          className={`rounded-lg px-4 py-2 ${
            isUser
              ? 'bg-blue-600 text-white'
              : 'bg-gray-100 dark:bg-gray-800 text-gray-900 dark:text-gray-100'
          }`}
        >
          {/* Render content with basic markdown support */}
          <MessageContent content={message.content} isUser={isUser} />
        </div>

        {/* Inline artifact viewers (only for assistant messages with artifacts) */}
        {linkedArtifacts.map((artifact) => (
          <InlineArtifactRenderer key={artifact.id} artifact={artifact} />
        ))}
      </div>
    </div>
  );
}

/**
 * Renders the appropriate inline viewer based on artifact type.
 */
function InlineArtifactRenderer({ artifact }: { artifact: PendingArtifact }) {
  switch (artifact.artifactType) {
    case ArtifactType.STRATEGY:
      return <InlineStrategyViewer artifact={artifact} />;
    default:
      // Unknown artifact type - don't render
      return null;
  }
}

interface MessageContentProps {
  content: string;
  isUser: boolean;
}

function MessageContent({ content, isUser }: MessageContentProps) {
  // Split by code blocks first
  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="text-sm break-words prose-sm max-w-none">
      {parts.map((part, index) => {
        // Check if this is a code block
        if (part.startsWith('```') && part.endsWith('```')) {
          const lines = part.slice(3, -3).split('\n');
          const language = lines[0].trim() || 'text';
          const code = lines.slice(1).join('\n');

          return (
            <pre
              key={index}
              className={`my-2 p-3 rounded-md overflow-x-auto text-xs font-mono ${
                isUser
                  ? 'bg-blue-700/50 text-blue-100'
                  : 'bg-gray-200 dark:bg-gray-700 text-gray-800 dark:text-gray-200'
              }`}
            >
              <div className="text-[10px] uppercase tracking-wider opacity-60 mb-1">
                {language}
              </div>
              <code>{code}</code>
            </pre>
          );
        }

        // Parse markdown blocks (headers, lists, paragraphs)
        return <MarkdownBlock key={index} content={part} isUser={isUser} />;
      })}
    </div>
  );
}

interface MarkdownBlockProps {
  content: string;
  isUser: boolean;
}

function MarkdownBlock({ content, isUser }: MarkdownBlockProps) {
  // Split into lines and process
  const lines = content.split('\n');
  const elements: React.ReactNode[] = [];
  let currentList: { type: 'ul' | 'ol'; items: string[] } | null = null;
  let listKey = 0;

  const flushList = () => {
    if (currentList) {
      const ListTag = currentList.type === 'ul' ? 'ul' : 'ol';
      elements.push(
        <ListTag
          key={`list-${listKey++}`}
          className={`my-2 ${currentList.type === 'ul' ? 'list-disc' : 'list-decimal'} list-inside space-y-1`}
        >
          {currentList.items.map((item, i) => (
            <li key={i}>
              <InlineMarkdown content={item} isUser={isUser} />
            </li>
          ))}
        </ListTag>
      );
      currentList = null;
    }
  };

  lines.forEach((line, lineIndex) => {
    const trimmedLine = line.trim();

    // Empty line
    if (!trimmedLine) {
      flushList();
      return;
    }

    // Headers
    const headerMatch = trimmedLine.match(/^(#{1,6})\s+(.+)$/);
    if (headerMatch) {
      flushList();
      const level = headerMatch[1].length;
      const text = headerMatch[2];
      const headerClasses: Record<number, string> = {
        1: 'text-xl font-bold mt-4 mb-2',
        2: 'text-lg font-semibold mt-3 mb-2',
        3: 'text-base font-semibold mt-2 mb-1',
        4: 'text-sm font-semibold mt-2 mb-1',
        5: 'text-sm font-medium mt-1 mb-1',
        6: 'text-xs font-medium mt-1 mb-1',
      };
      elements.push(
        <div key={`h-${lineIndex}`} className={headerClasses[level]}>
          <InlineMarkdown content={text} isUser={isUser} />
        </div>
      );
      return;
    }

    // Horizontal rule
    if (/^[-*_]{3,}$/.test(trimmedLine)) {
      flushList();
      elements.push(
        <hr
          key={`hr-${lineIndex}`}
          className={`my-3 border-t ${isUser ? 'border-blue-400/30' : 'border-gray-300 dark:border-gray-600'}`}
        />
      );
      return;
    }

    // Unordered list
    const ulMatch = trimmedLine.match(/^[-*+]\s+(.+)$/);
    if (ulMatch) {
      if (currentList?.type !== 'ul') {
        flushList();
        currentList = { type: 'ul', items: [] };
      }
      currentList.items.push(ulMatch[1]);
      return;
    }

    // Ordered list
    const olMatch = trimmedLine.match(/^\d+[.)]\s+(.+)$/);
    if (olMatch) {
      if (currentList?.type !== 'ol') {
        flushList();
        currentList = { type: 'ol', items: [] };
      }
      currentList.items.push(olMatch[1]);
      return;
    }

    // Regular paragraph
    flushList();
    elements.push(
      <p key={`p-${lineIndex}`} className="my-1">
        <InlineMarkdown content={line} isUser={isUser} />
      </p>
    );
  });

  // Flush any remaining list
  flushList();

  return <>{elements}</>;
}

interface InlineMarkdownProps {
  content: string;
  isUser: boolean;
}

function InlineMarkdown({ content, isUser }: InlineMarkdownProps) {
  // Pattern for bold, italic, inline code, and links
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  const parts = content.split(pattern);

  return (
    <>
      {parts.map((segment, index) => {
        // Bold
        if (segment.startsWith('**') && segment.endsWith('**')) {
          return <strong key={index}>{segment.slice(2, -2)}</strong>;
        }
        // Italic
        if (segment.startsWith('*') && segment.endsWith('*') && !segment.startsWith('**')) {
          return <em key={index}>{segment.slice(1, -1)}</em>;
        }
        // Inline code
        if (segment.startsWith('`') && segment.endsWith('`')) {
          return (
            <code
              key={index}
              className={`px-1 py-0.5 rounded text-xs font-mono ${
                isUser
                  ? 'bg-blue-700/50'
                  : 'bg-gray-200 dark:bg-gray-700'
              }`}
            >
              {segment.slice(1, -1)}
            </code>
          );
        }
        // Links
        const linkMatch = segment.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        if (linkMatch) {
          return (
            <a
              key={index}
              href={linkMatch[2]}
              target="_blank"
              rel="noopener noreferrer"
              className={`underline ${
                isUser
                  ? 'text-blue-200 hover:text-white'
                  : 'text-blue-600 dark:text-blue-400 hover:text-blue-800 dark:hover:text-blue-300'
              }`}
            >
              {linkMatch[1]}
            </a>
          );
        }
        return segment;
      })}
    </>
  );
}
