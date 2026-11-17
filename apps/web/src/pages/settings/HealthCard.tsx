import { AlertTriangle, Check, PlugZap } from 'lucide-react';
import { Link } from 'react-router-dom';

import type { HealthSummary } from './health';

const FIX_PATH = '/settings/broker';
const CONNECT_PATH = '/connect/alpaca?next=/settings/broker';

/**
 * Whether anything about the broker needs the person: amber with the fix one tap away, or one
 * small line on an ordinary day (phone2 A).
 */
export function HealthCard({ summary }: { summary: HealthSummary }) {
  if (summary.tone === 'risk') {
    return (
      <div
        role="alert"
        className="flex flex-col gap-3 rounded-[10px] border border-risk-line bg-risk-soft px-4 py-3 text-[13px] text-fg-2 md:flex-row md:items-center"
      >
        <AlertTriangle aria-hidden="true" className="hidden h-4 w-4 flex-none text-risk md:block" />
        <div className="min-w-0 flex-1">
          <b className="flex items-center gap-2 font-semibold text-fg md:inline">
            <AlertTriangle aria-hidden="true" className="h-4 w-4 flex-none text-risk md:hidden" />
            {summary.title}
          </b>{' '}
          <span className="mt-1 block md:mt-0 md:inline">{summary.body}</span>
        </div>
        <Link to={FIX_PATH} className="btn btn-primary btn-sm flex-none self-start md:self-auto">
          Fix the keys
        </Link>
      </div>
    );
  }
  const Icon = summary.tone === 'ok' ? Check : PlugZap;
  return (
    <div className="flex items-center gap-3 rounded-[10px] border border-line bg-panel px-4 py-3 text-[13px]">
      <Icon aria-hidden="true" className="h-4 w-4 flex-none text-fg-2" />
      <div className="min-w-0 flex-1">
        <b className="font-semibold text-fg">{summary.title}</b>{' '}
        <span className="text-fg-3">{summary.body}</span>
      </div>
      {summary.tone === 'none' && (
        <Link to={CONNECT_PATH} className="btn btn-secondary btn-sm flex-none">
          Connect Alpaca
        </Link>
      )}
    </div>
  );
}
