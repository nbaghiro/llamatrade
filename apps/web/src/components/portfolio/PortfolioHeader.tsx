/**
 * Portfolio page title, account identity subtitle, and live market-status pill.
 */

import { ExecutionMode, MarketStatus } from '../../store/portfolio';

interface PortfolioHeaderProps {
  mode: ExecutionMode;
  holderName: string;
  accountRef: string;
  openPositions: number;
  marketStatus: MarketStatus | null;
  marketNextOpen: Date | null;
  marketNextClose: Date | null;
}

type PillTone = 'open' | 'closed' | 'ext';
interface PillState {
  label: string;
  tone: PillTone;
}

function etNow(): { hour: number; minute: number; weekday: string; timeLabel: string } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false,
    weekday: 'short',
  }).formatToParts(new Date());
  let hour = Number(parts.find((p) => p.type === 'hour')?.value ?? '0');
  const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? '0');
  const weekday = parts.find((p) => p.type === 'weekday')?.value ?? '';
  hour = hour % 24; // Some engines emit "24" at midnight.
  return { hour, minute, weekday, timeLabel: `${hour}:${String(minute).padStart(2, '0')} ET` };
}

function countdown(target: Date): string {
  const mins = Math.max(0, Math.round((target.getTime() - Date.now()) / 60000));
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/**
 * Prefer the market-data clock RPC; when it is unavailable, derive open/closed
 * from the browser's ET clock (regular NYSE session 9:30–16:00 ET, Mon–Fri).
 */
function marketPill(
  status: MarketStatus | null,
  nextOpen: Date | null,
  nextClose: Date | null
): PillState {
  const { hour, minute, weekday, timeLabel } = etNow();

  if (status !== null && status !== MarketStatus.UNSPECIFIED) {
    switch (status) {
      case MarketStatus.OPEN:
        return {
          tone: 'open',
          label: `NYSE OPEN · ${timeLabel}${nextClose ? ` · closes in ${countdown(nextClose)}` : ''}`,
        };
      case MarketStatus.PRE_MARKET:
        return {
          tone: 'ext',
          label: `PRE-MARKET · ${timeLabel}${nextOpen ? ` · opens in ${countdown(nextOpen)}` : ''}`,
        };
      case MarketStatus.AFTER_HOURS:
        return {
          tone: 'ext',
          label: `AFTER HOURS · ${timeLabel}${nextOpen ? ` · opens in ${countdown(nextOpen)}` : ''}`,
        };
      default:
        return {
          tone: 'closed',
          label: `NYSE CLOSED · ${timeLabel}${nextOpen ? ` · opens in ${countdown(nextOpen)}` : ''}`,
        };
    }
  }

  const isWeekday = weekday !== 'Sat' && weekday !== 'Sun';
  const minutesOfDay = hour * 60 + minute;
  const openMin = 9 * 60 + 30;
  const closeMin = 16 * 60;
  if (isWeekday && minutesOfDay >= openMin && minutesOfDay < closeMin) {
    const left = closeMin - minutesOfDay;
    const h = Math.floor(left / 60);
    const m = left % 60;
    return { tone: 'open', label: `NYSE OPEN · ${timeLabel} · closes in ${h > 0 ? `${h}h ${m}m` : `${m}m`}` };
  }
  return { tone: 'closed', label: `NYSE CLOSED · ${timeLabel} · opens 9:30 ET` };
}

const DOT_TONE: Record<PillTone, string> = {
  open: 'bg-green-600',
  ext: 'bg-orange-500',
  closed: 'bg-ink/40',
};

export default function PortfolioHeader({
  mode,
  holderName,
  accountRef,
  openPositions,
  marketStatus,
  marketNextOpen,
  marketNextClose,
}: PortfolioHeaderProps) {
  const pill = marketPill(marketStatus, marketNextOpen, marketNextClose);
  const modeLabel = mode === ExecutionMode.LIVE ? 'Live' : 'Paper';

  return (
    <div className="flex items-end justify-between gap-4 flex-wrap">
      <div>
        <h1 className="font-display uppercase text-[44px] leading-[0.9] tracking-[0.01em] text-ink">
          Portfolio
        </h1>
        <div className="mt-2 flex items-center gap-2.5 font-mono text-xs text-ink/55 flex-wrap">
          <span
            className={`inline-flex items-center border-[1.5px] border-ink px-2 py-0.5 text-[10px] font-bold uppercase tracking-[0.08em] ${
              mode === ExecutionMode.LIVE ? 'bg-orange-500 text-ink' : 'bg-ink text-bone'
            }`}
          >
            {modeLabel}
          </span>
          {holderName && <span className="text-ink/70">{holderName}</span>}
          {accountRef && <span>· Account #{accountRef}</span>}
          <span>
            · <span className="tabular-nums">{openPositions}</span> open position
            {openPositions === 1 ? '' : 's'}
          </span>
        </div>
      </div>

      <span className="inline-flex items-center gap-2 border-2 border-ink bg-paper px-3 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.08em] text-ink">
        <span className={`w-2 h-2 rounded-full ${DOT_TONE[pill.tone]}`} />
        {pill.label}
      </span>
    </div>
  );
}
