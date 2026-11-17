import { AgentMessage, MessageRole, type PendingArtifact } from '@llamatrade/core/stores/agent';
import { useMemo, useState, type ReactNode } from 'react';

import { PendingArtifactCard } from './PendingArtifactCard';
import { CitationMark } from './SourcesPane';
import { ThinkingBlock } from './ThinkingBlock';
import { ToolCallIndicator } from './ToolCallIndicator';

interface ChatMessageProps {
  message: AgentMessage;
  /** Artifacts by id, for the strategy cards linked to this message. */
  artifacts?: Map<string, PendingArtifact>;
  /** Citation number of this message's first tool call; numbering runs across the thread. */
  firstSource?: number;
  activeSource?: number | null;
  onCite?: (n: number) => void;
  /** Starts long replies folded to three lines, for the phone's half sheet. */
  folded?: boolean;
}

const ET_TIME = new Intl.DateTimeFormat('en-US', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'America/New_York',
});

function etTime(seconds?: bigint): string {
  return seconds ? `${ET_TIME.format(new Date(Number(seconds) * 1000))} ET` : '';
}

function toolDetail(tc: AgentMessage['toolCalls'][number]): string {
  const raw = (tc.resultJson || tc.argumentsJson || '').replace(/[{}'"]/g, '').trim();
  return raw.length > 56 ? `${raw.slice(0, 56)}…` : raw;
}

/** One turn: the user's message on the right, Copilot's reply as plain reading text. */
export function ChatMessage({
  message,
  artifacts,
  firstSource,
  activeSource = null,
  onCite,
  folded = false,
}: ChatMessageProps) {
  const [open, setOpen] = useState(!folded);
  const isUser = message.role === MessageRole.USER;

  const linked = useMemo(() => {
    if (isUser || !message.inlineArtifactIds?.length || !artifacts) return [];
    return message.inlineArtifactIds
      .map((id) => artifacts.get(id))
      .filter((a): a is PendingArtifact => a !== undefined);
  }, [isUser, message.inlineArtifactIds, artifacts]);

  if (isUser) {
    return (
      <div className="grid justify-items-end">
        <div className="max-w-[80%] whitespace-pre-wrap break-words rounded-[10px] bg-fg px-[14px] py-[10px] text-[14px] text-canvas">
          {message.content}
        </div>
      </div>
    );
  }

  const calls = message.toolCalls ?? [];
  const cited = firstSource !== undefined && calls.length > 0;
  const when = etTime(message.createdAt?.seconds).replace(' ET', '');
  return (
    <div className="grid min-w-0 gap-2">
      <span className="flex flex-wrap items-baseline gap-x-2 font-mono text-[11px] font-medium text-fg-3">
        <span>Copilot</span>
        {when && <span>{when}</span>}
        {cited && (
          <button type="button" className="hover:text-accent" onClick={() => onCite?.(firstSource)}>
            · {calls.length === 1 ? '1 source' : `${calls.length} sources`}
          </button>
        )}
      </span>
      {message.thinking && <ThinkingBlock content={message.thinking} autoExpanded={false} />}
      {calls.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {calls.map((tc, i) => (
            <span
              key={tc.id || `${tc.name}-${i}`}
              className="inline-flex max-w-full items-center gap-1.5"
            >
              {cited && (
                <CitationMark
                  n={firstSource + i}
                  active={activeSource === firstSource + i}
                  onClick={() => onCite?.(firstSource + i)}
                />
              )}
              <ToolCallIndicator
                toolName={tc.name}
                status={tc.success ? 'complete' : 'error'}
                detail={cited ? undefined : toolDetail(tc)}
                durationMs={tc.durationMs}
              />
            </span>
          ))}
        </div>
      )}
      {!message.content && !calls.length && !linked.length && !message.thinking && (
        <p className="m-0 text-[13.5px] text-fg-3">
          Copilot didn&apos;t return an answer. Please ask again.
        </p>
      )}
      {message.content && (
        <div className={open ? '' : 'line-clamp-3'}>
          <MessageContent content={message.content} />
        </div>
      )}
      {!open && message.content && (
        <button
          type="button"
          className="justify-self-start text-[12.5px] font-medium text-accent"
          onClick={() => setOpen(true)}
        >
          Read more
        </button>
      )}
      {linked.map((artifact) => (
        <PendingArtifactCard key={artifact.id} artifact={artifact} />
      ))}
    </div>
  );
}

function MessageContent({ content }: { content: string }) {
  const parts = content.split(/(```[\s\S]*?```)/g);
  return (
    <div className="min-w-0 max-w-full break-words text-[14px] leading-[1.55] text-fg">
      {parts.map((part, i) => {
        if (part.startsWith('```') && part.endsWith('```')) {
          const lines = part.slice(3, -3).split('\n');
          return (
            <pre
              key={i}
              className="my-2 max-w-full overflow-x-auto rounded-[8px] bg-sunk px-3.5 py-2.5 font-mono text-[12.5px] leading-[1.7]"
            >
              <code>{lines.slice(1).join('\n')}</code>
            </pre>
          );
        }
        return <MarkdownBlock key={i} content={part} />;
      })}
    </div>
  );
}

const HEADING: Record<number, string> = {
  1: 'mb-2 mt-3 text-[17px] font-semibold',
  2: 'mb-1.5 mt-3 text-[15px] font-semibold',
  3: 'mb-1 mt-2 text-[14px] font-semibold',
};

function MarkdownBlock({ content }: { content: string }) {
  const elements: ReactNode[] = [];
  let list: { type: 'ul' | 'ol'; items: string[] } | null = null;
  let listKey = 0;

  const flush = () => {
    if (!list) return;
    const Tag = list.type;
    elements.push(
      <Tag
        key={`list-${listKey++}`}
        className={`my-2 grid gap-1 pl-5 ${list.type === 'ul' ? 'list-disc' : 'list-decimal'}`}
      >
        {list.items.map((item, i) => (
          <li key={i}>
            <InlineMarkdown content={item} />
          </li>
        ))}
      </Tag>
    );
    list = null;
  };

  content.split('\n').forEach((line, i) => {
    const t = line.trim();
    if (!t) {
      flush();
      return;
    }
    const heading = t.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      flush();
      elements.push(
        <div key={`h-${i}`} className={HEADING[Math.min(heading[1].length, 3)]}>
          <InlineMarkdown content={heading[2]} />
        </div>
      );
      return;
    }
    if (/^[-*_]{3,}$/.test(t)) {
      flush();
      elements.push(<hr key={`hr-${i}`} className="my-3 border-line" />);
      return;
    }
    const ul = t.match(/^[-*+]\s+(.+)$/);
    const ol = t.match(/^\d+[.)]\s+(.+)$/);
    if (ul || ol) {
      const type = ul ? 'ul' : 'ol';
      if (list?.type !== type) {
        flush();
        list = { type, items: [] };
      }
      list.items.push((ul ?? ol)?.[1] ?? '');
      return;
    }
    flush();
    elements.push(
      <p key={`p-${i}`} className="mb-2 mt-0 last:mb-0">
        <InlineMarkdown content={line} />
      </p>
    );
  });
  flush();
  return <>{elements}</>;
}

function InlineMarkdown({ content }: { content: string }) {
  const parts = content.split(/(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g);
  return (
    <>
      {parts.map((seg, i) => {
        if (seg.startsWith('**') && seg.endsWith('**')) {
          return <strong key={i}>{seg.slice(2, -2)}</strong>;
        }
        if (seg.startsWith('*') && seg.endsWith('*') && seg.length > 2) {
          return <em key={i}>{seg.slice(1, -1)}</em>;
        }
        if (seg.startsWith('`') && seg.endsWith('`')) {
          return (
            <code key={i} className="rounded-[4px] bg-sunk px-1 py-0.5 font-mono text-[12.5px]">
              {seg.slice(1, -1)}
            </code>
          );
        }
        const link = seg.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
        if (link) {
          const safe = /^(https?:|\/)/.test(link[2]);
          return safe ? (
            <a
              key={i}
              href={link[2]}
              target={link[2].startsWith('/') ? undefined : '_blank'}
              rel="noopener noreferrer"
              className="text-accent underline underline-offset-2"
            >
              {link[1]}
            </a>
          ) : (
            link[1]
          );
        }
        return seg;
      })}
    </>
  );
}
