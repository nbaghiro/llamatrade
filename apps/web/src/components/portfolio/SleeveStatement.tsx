import type { SleeveSummary } from '@llamatrade/core/stores/portfolio';
import { Link, useNavigate } from 'react-router-dom';

import { formatMoney } from '../../lib/format';
import { dayChange, weightRows } from '../../lib/portfolioView';
import { ModeBadge, Money, Num, StatusMark } from '../ui';

import { shortDate, sinceStart, sleeveColor, sleeveRunState } from './sleeveView';

interface SleeveStatementProps {
  /** Each sleeve with its index in the full list, so colours stay put when filtered. */
  sleeves: readonly { sleeve: SleeveSummary; index: number }[];
  /** Paper unallocated cash; null leaves the row out. */
  unallocated: number | null;
  /** "Live $48,210.55 + paper $80,195.57", under the rows. */
  footnote: string;
}

const TH =
  'border-b border-line px-3 py-2.5 text-left font-mono text-[11px] font-medium uppercase tracking-[0.06em] text-fg-3';
const TD = 'border-b border-line px-3 py-3 align-middle';

function Holds({ sleeve }: { sleeve: SleeveSummary }) {
  const rows = weightRows(sleeve.holdings, sleeve.value);
  const cash = sleeve.value > 0 && sleeve.cash !== null ? sleeve.cash / sleeve.value : 0;
  if (rows.length === 0) {
    return (
      <div>
        <div className="h-1.5 w-[120px] rounded-full border border-dashed border-fg-3" />
        <div className="mt-1 font-mono text-[11.5px] text-fg-3">
          {sleeveRunState(sleeve) === 'stopped' ? 'Cash' : 'No positions yet'}
        </div>
      </div>
    );
  }
  const shown = rows.slice(0, 4);
  return (
    <div>
      <div className="flex h-1.5 w-[120px] gap-px overflow-hidden rounded-full">
        {shown.map((r, i) => (
          <i
            key={r.holding.symbol}
            className="block h-full"
            style={{
              width: `${r.weight * 100}%`,
              background: `rgb(var(--fg) / ${0.85 - i * 0.18})`,
            }}
          />
        ))}
      </div>
      <div className="mt-1 truncate font-mono text-[11.5px] text-fg-2">
        {shown.map((r) => r.holding.symbol).join(' ')}
        {rows.length > shown.length && ` +${rows.length - shown.length}`}
        {cash >= 0.05 && <span className="text-fg-3"> · {(cash * 100).toFixed(1)}% cash</span>}
      </div>
    </div>
  );
}

/** Every sleeve with what was added, its value, today and its gain, adding up to the total. */
export function SleeveStatement({ sleeves, unallocated, footnote }: SleeveStatementProps) {
  const navigate = useNavigate();
  const added = sleeves.reduce((s, x) => s + x.sleeve.allocatedCapital, 0) + (unallocated ?? 0);
  const value = sleeves.reduce((s, x) => s + x.sleeve.value, 0) + (unallocated ?? 0);
  const today = sleeves.reduce((s, x) => s + dayChange(x.sleeve.value, x.sleeve.dayReturnPct), 0);
  const gain = sleeves.reduce((s, x) => s + sinceStart(x.sleeve), 0);
  const open = (s: SleeveSummary) => {
    if (s.sleeveId) navigate(`/portfolio/sleeves/${s.sleeveId}`);
  };

  return (
    <div className="panel overflow-hidden">
      <table className="w-full border-collapse text-[13px] max-md:hidden">
        <thead>
          <tr>
            <th className={TH}>Sleeve</th>
            <th className={TH}>Account</th>
            <th className={TH}>Status</th>
            <th className={TH}>Holds</th>
            <th className={`${TH} text-right`}>Added</th>
            <th className={`${TH} text-right`}>Value</th>
            <th className={`${TH} text-right`}>Today</th>
            <th className={`${TH} text-right`}>Gain</th>
          </tr>
        </thead>
        <tbody>
          {sleeves.map(({ sleeve: s, index }) => (
            <tr
              key={s.executionId}
              onClick={() => open(s)}
              className={s.sleeveId ? 'cursor-pointer hover:bg-sunk' : ''}
            >
              <td className={TD}>
                <div className="flex items-start gap-2.5">
                  <i
                    aria-hidden="true"
                    className="mt-1.5 h-2 w-2 flex-none rounded-[2px]"
                    style={{ background: sleeveColor(index) }}
                  />
                  <div className="min-w-0">
                    {s.sleeveId ? (
                      <Link
                        to={`/portfolio/sleeves/${s.sleeveId}`}
                        onClick={(e) => e.stopPropagation()}
                        className="font-medium text-fg hover:underline"
                      >
                        {s.name}
                      </Link>
                    ) : (
                      <span className="font-medium">{s.name}</span>
                    )}
                    {s.startedAt && (
                      <div className="text-[12px] text-fg-3">Since {shortDate(s.startedAt)}</div>
                    )}
                  </div>
                </div>
              </td>
              <td className={TD}>
                <ModeBadge mode={s.live ? 'live' : 'paper'} size="sm" />
              </td>
              <td className={TD}>
                <StatusMark state={sleeveRunState(s)} />
              </td>
              <td className={TD}>
                <Holds sleeve={s} />
              </td>
              <td className={`${TD} text-right text-fg-2`}>
                <Num value={s.allocatedCapital} />
              </td>
              <td className={`${TD} text-right`}>
                <Money value={s.value} />
              </td>
              <td className={`${TD} text-right`}>
                <Money value={dayChange(s.value, s.dayReturnPct)} pnl />
              </td>
              <td className={`${TD} text-right`}>
                <Money value={sinceStart(s)} pnl />
              </td>
            </tr>
          ))}
          {unallocated !== null && (
            <tr>
              <td className={TD}>
                <div className="flex items-start gap-2.5">
                  <i
                    aria-hidden="true"
                    className="mt-1.5 h-2 w-2 flex-none rounded-[2px] border border-dashed border-fg-3"
                  />
                  <div>
                    <span className="font-medium">Unallocated</span>
                    <div className="text-[12px] text-fg-3">Paper cash</div>
                  </div>
                </div>
              </td>
              <td className={TD}>
                <ModeBadge mode="paper" size="sm" />
              </td>
              <td className={`${TD} text-fg-3`} colSpan={2}>
                {unallocated > 0 ? 'Waiting to be deployed' : 'Nothing waiting'}
              </td>
              <td className={`${TD} text-right text-fg-3`}>·</td>
              <td className={`${TD} text-right`}>
                <Money value={unallocated} />
              </td>
              <td className={`${TD} text-right text-fg-3`}>·</td>
              <td className={`${TD} text-right text-fg-3`}>·</td>
            </tr>
          )}
        </tbody>
        <tfoot>
          <tr className="font-semibold">
            <td className="px-3 py-3 font-normal text-fg-2" colSpan={4}>
              {footnote}
            </td>
            <td className="px-3 py-3 text-right">
              <Money value={added} />
            </td>
            <td className="px-3 py-3 text-right">
              <Money value={value} />
            </td>
            <td className="px-3 py-3 text-right">
              <Money value={today} pnl />
            </td>
            <td className="px-3 py-3 text-right">
              <Money value={gain} pnl />
            </td>
          </tr>
        </tfoot>
      </table>

      <div className="md:hidden">
        {sleeves.map(({ sleeve: s, index }) => (
          <button
            key={s.executionId}
            type="button"
            onClick={() => open(s)}
            className="flex w-full items-center justify-between gap-3 border-b border-line px-4 py-3 text-left"
          >
            <span className="min-w-0">
              <span className="flex items-center gap-2">
                <i
                  aria-hidden="true"
                  className="h-2 w-2 flex-none rounded-[2px]"
                  style={{ background: sleeveColor(index) }}
                />
                <span className="truncate font-medium">{s.name}</span>
                <ModeBadge mode={s.live ? 'live' : 'paper'} size="sm" />
              </span>
              <span className="mt-0.5 block text-[12.5px] text-fg-3">
                <StatusMark state={sleeveRunState(s)} />
              </span>
            </span>
            <span className="text-right">
              <Money value={s.value} className="block" />
              <Money value={sinceStart(s)} pnl className="text-[12.5px]" />
            </span>
          </button>
        ))}
        {unallocated !== null && (
          <div className="flex items-center justify-between border-b border-line px-4 py-3">
            <span>Unallocated</span>
            <Money value={unallocated} />
          </div>
        )}
        <div className="flex items-center justify-between px-4 py-3 font-semibold">
          <span>Total</span>
          <span className="num">{formatMoney(value)}</span>
        </div>
      </div>
    </div>
  );
}
