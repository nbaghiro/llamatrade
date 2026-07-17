/** Copilot chat turn: ink user bubble / paper assistant bubble, tool rows, inline artifacts. */

import { AgentMessage, MessageRole, type PendingArtifact } from '@llamatrade/core/stores/agent';
import { Sparkles } from 'lucide-react';
import { useMemo } from 'react';

import { useAuthStore } from '../../store/auth';

import { PendingArtifactCard } from './PendingArtifactCard';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolCallIndicator } from './ToolCallIndicator';

interface ChatMessageProps {
  message: AgentMessage;
  /** Map of artifact ID to artifact data for inline rendering */
  artifacts?: Map<string, PendingArtifact>;
}

/** Format a proto Timestamp into a compact "9:47 ET" label. */
function formatTime(seconds?: bigint): string {
  if (!seconds) return '';
  const d = new Date(Number(seconds) * 1000);
  const h = d.getHours();
  const m = d.getMinutes().toString().padStart(2, '0');
  return `${h}:${m} ET`;
}

/** Condense a tool call's args/result into a short dim summary. */
function toolDetail(tc: AgentMessage['toolCalls'][number]): string {
  const raw = (tc.resultJson || tc.argumentsJson || '').replace(/[{}'"]/g, '').trim();
  return raw.length > 56 ? `${raw.slice(0, 56)}…` : raw;
}

export function ChatMessage({ message, artifacts }: ChatMessageProps) {
  const isUser = message.role === MessageRole.USER;
  const firstName = useAuthStore((s) => s.user?.firstName);

  const linkedArtifacts = useMemo(() => {
    if (isUser || !message.inlineArtifactIds?.length || !artifacts) return [];
    return message.inlineArtifactIds
      .map((id) => artifacts.get(id))
      .filter((a): a is PendingArtifact => a !== undefined);
  }, [isUser, message.inlineArtifactIds, artifacts]);

  const time = formatTime(message.createdAt?.seconds);
  const label = isUser ? [firstName || 'You', time].filter(Boolean).join(' · ') : 'Copilot';

  return (
    <div className={`flex gap-3.5 ${isUser ? 'flex-row-reverse' : ''}`}>
      <div
        className={`h-9 w-9 flex-none border-2 border-ink ${
          isUser ? 'bg-gradient-to-br from-orange-300 to-orange-500' : 'grid place-items-center bg-ink'
        }`}
      >
        {!isUser && <Sparkles className="h-4 w-4 text-orange-500" />}
      </div>

      <div className={`flex min-w-0 max-w-[80%] flex-col gap-2.5 ${isUser ? 'items-end' : 'items-start'}`}>
        <span className="font-mono text-[9.5px] font-bold uppercase tracking-[0.1em] text-ink/45">{label}</span>

        {!isUser && message.thinking && (
          <ThinkingBlock content={message.thinking} autoExpanded={false} />
        )}

        <div
          className={`min-w-0 max-w-full border-2 px-4 py-3 text-sm leading-relaxed ${
            isUser
              ? 'border-orange-500 bg-ink text-bone shadow-[4px_4px_0_rgb(var(--lt-orange-500))]'
              : 'border-ink bg-paper text-ink shadow-[4px_4px_0_rgb(var(--lt-ink))]'
          }`}
        >
          <MessageContent content={message.content} isUser={isUser} />
        </div>

        {/* Tool calls recorded on this message (historical sessions). */}
        {!isUser &&
          message.toolCalls?.map((tc) => (
            <ToolCallIndicator
              key={tc.id || tc.name}
              toolName={tc.name}
              status={tc.success ? 'complete' : 'error'}
              detail={toolDetail(tc)}
              durationMs={tc.durationMs}
            />
          ))}

        {/* Inline strategy artifacts linked to this message. */}
        {linkedArtifacts.map((artifact) => (
          <PendingArtifactCard key={artifact.id} artifact={artifact} />
        ))}
      </div>
    </div>
  );
}

interface MessageContentProps {
  content: string;
  isUser: boolean;
}

function MessageContent({ content, isUser }: MessageContentProps) {
  const parts = content.split(/(```[\s\S]*?```)/g);

  return (
    <div className="min-w-0 max-w-full break-words text-sm">
      {parts.map((part, index) => {
        if (part.startsWith('```') && part.endsWith('```')) {
          const lines = part.slice(3, -3).split('\n');
          const language = lines[0].trim() || 'text';
          const code = lines.slice(1).join('\n');
          return (
            <pre
              key={index}
              className={`my-2 max-w-full overflow-x-auto p-3 font-mono text-xs ${
                isUser ? 'border border-bone/30 bg-ink/70 text-bone' : 'border border-ink bg-bone text-ink'
              }`}
            >
              <div className="mb-1 text-[10px] uppercase tracking-wider opacity-60">{language}</div>
              <code>{code}</code>
            </pre>
          );
        }
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
    if (!trimmedLine) {
      flushList();
      return;
    }

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

    if (/^[-*_]{3,}$/.test(trimmedLine)) {
      flushList();
      elements.push(
        <hr key={`hr-${lineIndex}`} className={`my-3 border-t ${isUser ? 'border-bone/30' : 'border-ink/20'}`} />
      );
      return;
    }

    const ulMatch = trimmedLine.match(/^[-*+]\s+(.+)$/);
    if (ulMatch) {
      if (currentList?.type !== 'ul') {
        flushList();
        currentList = { type: 'ul', items: [] };
      }
      currentList.items.push(ulMatch[1]);
      return;
    }

    const olMatch = trimmedLine.match(/^\d+[.)]\s+(.+)$/);
    if (olMatch) {
      if (currentList?.type !== 'ol') {
        flushList();
        currentList = { type: 'ol', items: [] };
      }
      currentList.items.push(olMatch[1]);
      return;
    }

    flushList();
    elements.push(
      <p key={`p-${lineIndex}`} className="my-1">
        <InlineMarkdown content={line} isUser={isUser} />
      </p>
    );
  });

  flushList();
  return <>{elements}</>;
}

interface InlineMarkdownProps {
  content: string;
  isUser: boolean;
}

function InlineMarkdown({ content, isUser }: InlineMarkdownProps) {
  const pattern = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  const parts = content.split(pattern);

  return (
    <>
      {parts.map((segment, index) => {
        if (segment.startsWith('**') && segment.endsWith('**')) {
          return <strong key={index}>{segment.slice(2, -2)}</strong>;
        }
        if (segment.startsWith('*') && segment.endsWith('*') && !segment.startsWith('**')) {
          return <em key={index}>{segment.slice(1, -1)}</em>;
        }
        if (segment.startsWith('`') && segment.endsWith('`')) {
          return (
            <code
              key={index}
              className={`px-1 py-0.5 font-mono text-xs font-bold ${
                isUser ? 'bg-bone/20 text-bone' : 'border border-line bg-bone text-ink'
              }`}
            >
              {segment.slice(1, -1)}
            </code>
          );
        }
        const linkMatch = segment.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        if (linkMatch) {
          return (
            <a
              key={index}
              href={linkMatch[2]}
              target="_blank"
              rel="noopener noreferrer"
              className={`underline ${isUser ? 'text-orange-400 hover:text-orange-300' : 'text-blue-600 hover:text-blue-800'}`}
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
