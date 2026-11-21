import { Clock, RefreshCw } from 'lucide-react';
import type { ReactNode } from 'react';

import { formatMoney, formatPct, pnlTone } from '../../lib/format';
import { etClock } from '../../lib/marketClock';

/** A signed figure in the gain or loss tone, as plain text. */
export function Chg({ children, value }: { children: ReactNode; value: number }) {
  const tone = pnlTone(value);
  const cls = tone === 'gain' ? 'text-gain' : tone === 'loss' ? 'text-loss' : 'text-fg-2';
  return <span className={`font-mono text-[12.5px] font-medium ${cls}`}>{children}</span>;
}

export function Label({ children }: { children: ReactNode }) {
  return (
    <div className="font-mono text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">
      {children}
    </div>
  );
}

export interface HeroFigures {
  /** "paper and live", "paper" or "live". */
  kinds: string;
  total: number;
  today: number | null;
  todayPct: number | null;
  cash: number | null;
  live: number;
  paper: number;
  showSplit: boolean;
  /** Set when the figures are from an earlier load that couldn't refresh. */
  staleSince: Date | null;
  onRetry: () => void;
  retrying: boolean;
}

export interface HomeHeadProps {
  figures: HeroFigures;
  date: string;
  /** Sessions, the market and what needs attention, in one line. */
  sub: string;
  /** SPY's move on the day shown, as a fraction, with the words for that day. */
  spy: { value: number | null; when: string };
  /** False while the market is closed: the figures are at the last close. */
  open: boolean;
  /** Shown in place of the figures when the account couldn't be loaded. */
  failed?: ReactNode;
}

/** The account figure, today's change against SPY, and the live and paper split. */
export function HomeHead({ figures, date, sub, spy, open, failed }: HomeHeadProps) {
  return (
    <section aria-label="Account" className="min-w-0">
      <div className="min-w-0">
        <div className="text-[13px] text-fg-2">
          <b className="font-semibold text-fg">{date}</b> ·{' '}
          {open ? `${capitalise(figures.kinds)} on Alpaca` : `At the close, ${figures.kinds}`}
        </div>
        {failed ?? (
          <>
            <div className="mt-2 font-mono text-[34px] font-semibold leading-none tracking-[-0.04em] text-fg md:text-[40px]">
              {formatMoney(figures.total)}
            </div>
            <div className="mt-2.5 flex flex-wrap items-baseline gap-x-5 gap-y-1 text-[13px] text-fg-2">
              {figures.today !== null && (
                <span>
                  <Chg value={figures.today}>
                    {formatMoney(figures.today, { signed: true })}
                    {figures.todayPct !== null &&
                      ` (${formatPct(figures.todayPct, { signed: true })})`}
                  </Chg>{' '}
                  {open ? 'today' : spy.when}
                </span>
              )}
              <span>
                SPY{' '}
                {spy.value === null ? (
                  <span className="text-fg-3">no data</span>
                ) : (
                  <Chg value={spy.value * 100}>{formatPct(spy.value, { signed: true })}</Chg>
                )}
              </span>
              {figures.showSplit && (
                <>
                  <span>
                    Live <span className="font-mono text-fg">{formatMoney(figures.live)}</span>
                  </span>
                  <span>
                    Paper <span className="font-mono text-fg">{formatMoney(figures.paper)}</span>
                  </span>
                </>
              )}
              {figures.cash !== null && (
                <span>
                  Cash <span className="font-mono text-fg">{formatMoney(figures.cash)}</span>
                </span>
              )}
            </div>
            {figures.staleSince && (
              <div className="mt-2 flex flex-wrap items-center gap-2 text-[12px] text-fg-2">
                <Clock aria-hidden="true" className="h-3.5 w-3.5 text-fg-3" />
                From {etClock(figures.staleSince)}. Couldn&apos;t refresh.
                <button
                  type="button"
                  onClick={figures.onRetry}
                  disabled={figures.retrying}
                  className="btn btn-secondary btn-sm"
                >
                  <RefreshCw aria-hidden="true" className="h-3.5 w-3.5" />
                  Try again
                </button>
              </div>
            )}
          </>
        )}
        <p className="m-0 mt-2 text-[12.5px] text-fg-3">{sub}</p>
      </div>
    </section>
  );
}

const capitalise = (s: string) => (s ? `${s[0].toUpperCase()}${s.slice(1)}` : s);

export function NoHistory() {
  return (
    <div className="grid min-h-[200px] place-content-center gap-1 rounded-[8px] border border-dashed border-line px-6 text-center text-[13px]">
      <b className="font-semibold text-fg">No daily history yet</b>
      <span className="text-fg-2">The account line appears after two daily snapshots.</span>
    </div>
  );
}
