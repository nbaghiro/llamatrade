import { AgentMessage, MessageRole, type PendingArtifact } from '@llamatrade/core/stores/agent';
import { AlertTriangle, Check, ChevronDown } from 'lucide-react';
import { useMemo, useState, type ReactNode } from 'react';

import { CopilotMark } from '../common/Logo';

import { readSummary, splitCitations } from './citations';
import { DraftChoices } from './DraftChoices';
import {
  answersMessage,
  DEFAULTS_MESSAGE,
  parseDraftQuestions,
  stripDraftInstruction,
} from './draftQuestions';
import { PendingArtifactCard } from './PendingArtifactCard';
import { CitationMark, SourceChips } from './SourceMarks';
import type { SourceView } from './sources';
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
  /** Questions to ask next, shown as chips under the answer. */
  followUps?: readonly string[];
  onAsk?: (question: string) => void;
  /** Sends the reply to a questions-first card; without it the card is shown read-only. */
  onReply?: (text: string) => void;
  /** The person already replied after this message. */
  replied?: boolean;
  /** This message's sources, listed under the answer. */
  sources?: readonly SourceView[];
  /** A question kept because Copilot couldn't take it. */
  notSent?: boolean;
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

/** Maps a marker in this reply ("[2]", its second call) to its number across the thread. */
interface CiteProps {
  cite?: (n: number) => number | null;
  active: number | null;
  onCite?: (n: number) => void;
}

/** The person's message on the right; a question Copilot couldn't take is marked "Not sent". */
export function UserBubble({ text, notSent = false }: { text: string; notSent?: boolean }) {
  return (
    <div className="grid justify-items-end gap-1 motion-safe:animate-rise">
      <div
        className={`max-w-[78%] whitespace-pre-wrap break-words rounded-[14px_14px_4px_14px] bg-sunk px-[14px] py-[10px] text-[15px] leading-[1.55] text-fg ${notSent ? 'opacity-70' : ''}`}
      >
        {stripDraftInstruction(text)}
      </div>
      {notSent && <span className="text-[11.5px] text-fg-3">Not sent</span>}
    </div>
  );
}

/** One turn: the user's message on the right, Copilot's reply as plain reading text. */
export function ChatMessage({
  message,
  artifacts,
  firstSource,
  activeSource = null,
  onCite,
  followUps = [],
  onAsk,
  onReply,
  replied = false,
  sources = [],
  notSent = false,
}: ChatMessageProps) {
  const [reads, setReads] = useState(false);
  const isUser = message.role === MessageRole.USER;

  const linked = useMemo(() => {
    if (isUser || !message.inlineArtifactIds?.length || !artifacts) return [];
    return message.inlineArtifactIds
      .map((id) => artifacts.get(id))
      .filter((a): a is PendingArtifact => a !== undefined);
  }, [isUser, message.inlineArtifactIds, artifacts]);

  const ask = useMemo(
    () => (isUser ? null : parseDraftQuestions(message.content)),
    [isUser, message.content]
  );

  if (isUser) return <UserBubble text={message.content} notSent={notSent} />;

  const calls = message.toolCalls ?? [];
  const cited = firstSource !== undefined && calls.length > 0;
  const when = etTime(message.createdAt?.seconds).replace(' ET', '');
  const seconds =
    calls.reduce((sum, tc) => sum + (tc.durationMs > 0 ? tc.durationMs : 0), 0) / 1000;
  const allOk = calls.every((tc) => tc.success);
  const cite = cited
    ? (n: number) => (n >= 1 && n <= calls.length ? firstSource + n - 1 : null)
    : undefined;
  const text = ask ? ask.intro : message.content;
  return (
    <div className="grid min-w-0 gap-2.5 motion-safe:animate-rise">
      <span className="flex flex-wrap items-baseline gap-x-2 text-[12px] text-fg-3">
        <span className="flex items-center gap-2 self-center">
          <CopilotMark className="h-3.5 w-3.5 text-fg" />
          Copilot
        </span>
        {when && <span className="font-mono text-[11px]">{when}</span>}
        {cited && (
          <button type="button" className="hover:text-fg" onClick={() => onCite?.(firstSource)}>
            · {calls.length === 1 ? '1 source' : `${calls.length} sources`}
          </button>
        )}
      </span>
      {message.thinking && <ThinkingBlock content={message.thinking} autoExpanded={false} />}
      {calls.length > 0 && (
        <button
          type="button"
          aria-expanded={reads}
          onClick={() => setReads(!reads)}
          className="inline-flex h-7 max-w-full items-center gap-1.5 justify-self-start rounded-full border border-line px-2.5 text-[12px] text-fg-2 hover:border-line-strong"
        >
          {allOk ? (
            <Check className="h-3.5 w-3.5 flex-none text-fg-3" />
          ) : (
            <AlertTriangle className="h-3.5 w-3.5 flex-none text-risk" />
          )}
          <span className="truncate">{readSummary(calls.map((tc) => tc.name))}</span>
          {seconds > 0 && (
            <>
              <span className="text-fg-3">·</span>
              <b className="num font-medium">{seconds.toFixed(1)} s</b>
            </>
          )}
          <ChevronDown className={`h-3.5 w-3.5 flex-none text-fg-3 ${reads ? 'rotate-180' : ''}`} />
        </button>
      )}
      {reads && calls.length > 0 && (
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
      {text && <MessageContent content={text} cite={cite} active={activeSource} onCite={onCite} />}
      {ask && (
        <DraftChoices
          questions={ask.questions}
          answered={replied}
          disabled={!onReply}
          onDraft={(picks) => onReply?.(answersMessage(ask.questions, picks))}
          onDefaults={() => onReply?.(DEFAULTS_MESSAGE)}
        />
      )}
      {linked.map((artifact) => (
        <PendingArtifactCard key={artifact.id} artifact={artifact} />
      ))}
      {sources.length > 0 && (
        <SourceChips sources={sources} active={activeSource} onCite={onCite} />
      )}
      {followUps.length > 0 && onAsk && (
        <div className="flex flex-wrap gap-2 pt-1">
          {followUps.map((q) => (
            <button
              key={q}
              type="button"
              onClick={() => onAsk(q)}
              className="inline-flex min-h-[28px] items-center rounded-full border border-line-strong px-3 py-1 text-left text-[12.5px] text-fg-2 transition-colors hover:border-fg-3 hover:text-fg"
            >
              {q}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function MessageContent({ content, ...cites }: { content: string } & CiteProps) {
  const parts = content.split(/(```[\s\S]*?```)/g);
  return (
    <div className="min-w-0 max-w-full break-words text-[15px] leading-[1.65] text-fg">
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
        return <MarkdownBlock key={i} content={part} {...cites} />;
      })}
    </div>
  );
}

const HEADING: Record<number, string> = {
  1: 'mb-2 mt-3 text-[17px] font-semibold',
  2: 'mb-1.5 mt-3 text-[15px] font-semibold',
  3: 'mb-1 mt-2 text-[14px] font-semibold',
};

function MarkdownBlock({ content, ...cites }: { content: string } & CiteProps) {
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
            <InlineMarkdown content={item} {...cites} />
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
          <InlineMarkdown content={heading[2]} {...cites} />
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
        <InlineMarkdown content={line} {...cites} />
      </p>
    );
  });
  flush();
  return <>{elements}</>;
}

function Cited({ text, cite, active, onCite }: { text: string } & CiteProps) {
  const parts = splitCitations(text);
  if (parts.length === 1 && 'text' in parts[0]) return <>{text}</>;
  return (
    <>
      {parts.map((p, i) => {
        if ('text' in p) return <span key={i}>{p.text}</span>;
        const n = cite?.(p.n) ?? null;
        return n === null ? (
          <sup key={i} className="ml-0.5 font-mono text-[10.5px] text-fg-3">
            {p.n}
          </sup>
        ) : (
          <span key={i} className="ml-0.5">
            <CitationMark n={n} active={active === n} onClick={() => onCite?.(n)} />
          </span>
        );
      })}
    </>
  );
}

function InlineMarkdown({ content, ...cites }: { content: string } & CiteProps) {
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
              className="text-fg underline decoration-line-strong underline-offset-[3px] hover:decoration-fg"
            >
              {link[1]}
            </a>
          ) : (
            link[1]
          );
        }
        return <Cited key={i} text={seg} {...cites} />;
      })}
    </>
  );
}
