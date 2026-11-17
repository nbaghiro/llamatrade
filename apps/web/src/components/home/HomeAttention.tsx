import { Link } from 'react-router-dom';

import { AttentionLine, type AttentionItem } from '../ui';

import type { AttentionEntry } from './attention';

/** One amber line above Home. Several issues read as a count that opens into a list. */
export function HomeAttention({
  entries,
  className,
}: {
  entries: AttentionEntry[];
  className?: string;
}) {
  const items: AttentionItem[] = entries.map((e) => ({
    id: e.id,
    title: e.title,
    detail: e.detail,
    action: (
      <Link to={e.href} className="btn btn-secondary btn-sm flex-none">
        Review
      </Link>
    ),
  }));
  return <AttentionLine items={items} defaultOpen className={className} />;
}
