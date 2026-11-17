import type { ReactNode } from 'react';

import { formatMoney } from '../../lib/format';

interface PaperLiveSplitProps {
  live: number;
  paper: number;
  /** Lines under each figure, e.g. "1 session · +0.31% today". */
  liveDetail?: ReactNode;
  paperDetail?: ReactNode;
  /** figures: two small figures beside a total; bar: the figures over a split bar. */
  variant?: 'figures' | 'bar';
  className?: string;
}

const HATCH = 'repeating-linear-gradient(135deg, rgb(var(--accent)) 0 2px, transparent 2px 5px)';

function Swatch({ kind }: { kind: 'live' | 'paper' }) {
  return (
    <i
      aria-hidden="true"
      className={`inline-block h-2 w-2 flex-none ${kind === 'live' ? 'bg-fg' : ''}`}
      style={kind === 'paper' ? { backgroundImage: HATCH } : undefined}
    />
  );
}

function Figure({
  kind,
  value,
  detail,
  share,
}: {
  kind: 'live' | 'paper';
  value: number;
  detail?: ReactNode;
  share: number | null;
}) {
  return (
    <div className="min-w-0">
      <div className="flex items-center gap-1.5 font-mono text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">
        <Swatch kind={kind} />
        {kind === 'live' ? 'Live' : 'Paper'}
      </div>
      <div className="mt-0.5 font-mono text-[15px] font-semibold tracking-[-0.02em] text-fg">
        {formatMoney(value)}
      </div>
      {(detail || share !== null) && (
        <div className="mt-0.5 text-[11.5px] text-fg-3">
          {share !== null && <span className="font-mono">{(share * 100).toFixed(1)}%</span>}
          {share !== null && detail ? ' · ' : ''}
          {detail}
        </div>
      )}
    </div>
  );
}

/**
 * How much of a total is real money and how much is simulated (home/hero B). Live is solid
 * ink and paper is hatched accent, so the bar reads in one colour when everything is one kind.
 */
export function PaperLiveSplit({
  live,
  paper,
  liveDetail,
  paperDetail,
  variant = 'figures',
  className = '',
}: PaperLiveSplitProps) {
  const total = Math.max(0, live) + Math.max(0, paper);
  const liveShare = total > 0 ? Math.max(0, live) / total : 0;
  const showShare = variant === 'bar' && total > 0;
  return (
    <div className={className}>
      <div className="flex flex-wrap gap-x-7 gap-y-2">
        <Figure kind="live" value={live} detail={liveDetail} share={showShare ? liveShare : null} />
        <Figure
          kind="paper"
          value={paper}
          detail={paperDetail}
          share={showShare ? 1 - liveShare : null}
        />
      </div>
      {variant === 'bar' && total > 0 && (
        <div
          role="img"
          aria-label={`${(liveShare * 100).toFixed(1)}% live, ${((1 - liveShare) * 100).toFixed(1)}% paper`}
          className="mt-3 flex h-2 w-full gap-[3px] overflow-hidden"
        >
          {liveShare > 0 && <i className="h-full bg-fg" style={{ width: `${liveShare * 100}%` }} />}
          {liveShare < 1 && <i className="h-full flex-1" style={{ backgroundImage: HATCH }} />}
        </div>
      )}
    </div>
  );
}
