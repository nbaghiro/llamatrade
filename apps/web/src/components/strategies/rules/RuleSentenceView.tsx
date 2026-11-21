import { Link } from 'react-router-dom';

import type { SentencePart } from './ruleSentence';

const TERM =
  'cursor-pointer rounded-[3px] text-fg underline decoration-fg-3/70 decoration-dotted decoration-[1.5px] underline-offset-[5px] transition-colors hover:decoration-accent focus-visible:outline focus-visible:outline-2 focus-visible:outline-accent';
const OPEN = 'bg-accent-soft decoration-accent decoration-solid';

/**
 * The rules sentence with each value underlined. Terms open their rule through `onOpen`, or
 * link to `href(id)` when the sentence is only a summary.
 */
export function RuleSentenceView({
  parts,
  openId = null,
  onOpen,
  href,
  className = '',
}: {
  parts: readonly SentencePart[];
  openId?: string | null;
  onOpen?: (id: string) => void;
  href?: (id: string) => string;
  className?: string;
}) {
  return (
    <p className={`m-0 ${className}`}>
      {parts.map((p, i) => {
        if (p.kind === 'text') return <span key={i}>{p.text}</span>;
        const cls = `${TERM} ${openId === p.id ? OPEN : ''}`;
        if (href) {
          return (
            <Link key={p.id} to={href(p.id)} className={cls}>
              {p.text}
            </Link>
          );
        }
        return (
          <button
            key={p.id}
            type="button"
            aria-expanded={openId === p.id}
            onClick={() => onOpen?.(p.id)}
            className={`${cls} inline border-0 p-0 text-left font-[inherit] leading-[inherit] ${openId === p.id ? '' : 'bg-transparent'}`}
          >
            {p.text}
          </button>
        );
      })}
    </p>
  );
}
