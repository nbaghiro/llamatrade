import type { SleeveSummary } from '@llamatrade/core/stores/portfolio';
import { Link } from 'react-router-dom';

import { dayChange } from '../../lib/portfolioView';
import { Money, Num, StatusMark } from '../ui';

import { rebalanceLabel, sleeveColor, sleeveRunState } from './sleeveView';
import { WeightRows } from './WeightRows';

interface SleeveCardProps {
  sleeve: SleeveSummary;
  index: number;
}

/** One sleeve on the overview: status, value, today's change and schedule, then its funds. */
export function SleeveCard({ sleeve, index }: SleeveCardProps) {
  const state = sleeveRunState(sleeve);
  const today = dayChange(sleeve.value, sleeve.dayReturnPct);
  const title = (
    <span className="inline-flex min-w-0 items-center">
      <span
        aria-hidden="true"
        className="mr-2 inline-block h-[9px] w-[9px] flex-none rounded-[2px]"
        style={{ background: sleeveColor(index) }}
      />
      <b className="truncate font-semibold">{sleeve.name}</b>
    </span>
  );

  return (
    <section
      aria-label={sleeve.name}
      className={`rounded-panel border bg-panel ${sleeve.frozen ? 'border-risk-line' : 'border-line'}`}
    >
      <div className="flex items-center justify-between gap-2.5 border-b border-line px-4 py-3">
        {sleeve.sleeveId ? (
          <Link
            to={`/portfolio/sleeves/${sleeve.sleeveId}`}
            className="min-w-0 rounded-sm hover:text-accent"
          >
            {title}
          </Link>
        ) : (
          title
        )}
        <StatusMark state={state} />
      </div>
      <div className="px-4 pb-3.5 pt-2.5">
        <div className="mb-2 flex items-end justify-between gap-2.5">
          <div>
            <Num value={sleeve.value} className="block text-xl" />
            <span className="text-[12.5px]">
              <Money value={today} pnl /> <span className="text-fg-3">today</span>
            </span>
          </div>
          <div className="text-right text-[12.5px] text-fg-3">
            {rebalanceLabel(sleeve.rebalance)}
            {sleeve.frozen && <div>Orders held</div>}
          </div>
        </div>
        {sleeve.holdings.length > 0 ? (
          <WeightRows
            holdings={sleeve.holdings}
            sleeveValue={sleeve.value}
            targets={sleeve.targets}
            frozen={sleeve.frozen}
            phoneLimit={2}
          />
        ) : (
          <p className="m-0 py-1.5 text-[12.5px] text-fg-3">
            No open positions. This sleeve holds only cash right now.
          </p>
        )}
      </div>
    </section>
  );
}
