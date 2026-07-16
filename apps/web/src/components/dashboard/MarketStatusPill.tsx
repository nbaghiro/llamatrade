import { useEffect, useState } from 'react';

import { MarketStatus, useDashboardStore } from '../../store/dashboard';

const GREEN = '#0f7a34';
const ORANGE = '#ff4d1c';
const RED = '#c81e1e';

function etParts(d: Date): { hour: number; minute: number; isWeekday: boolean } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    hour12: false,
    hour: '2-digit',
    minute: '2-digit',
    weekday: 'short',
  }).formatToParts(d);
  const get = (t: string) => parts.find((p) => p.type === t)?.value ?? '';
  return {
    hour: Number(get('hour')) % 24,
    minute: Number(get('minute')),
    isWeekday: !['Sat', 'Sun'].includes(get('weekday')),
  };
}

function fmtCountdown(mins: number): string {
  if (mins <= 0) return '';
  const h = Math.floor(mins / 60);
  const m = mins % 60;
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}

/** "closes 6h 8m" for near targets, "opens Mon 9:30 ET" past a day out. */
function describeTarget(target: Date, verb: string, now: Date): string {
  const mins = Math.round((target.getTime() - now.getTime()) / 60_000);
  if (mins <= 0) return '';
  if (mins < 24 * 60) return `${verb} ${fmtCountdown(mins)}`;
  const dayFmt = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/New_York',
    weekday: 'short',
    hour: 'numeric',
    minute: '2-digit',
    hour12: false,
  });
  return `${verb} ${dayFmt.format(target)} ET`;
}

interface Pill {
  label: string;
  dot: string;
  tail: string;
}

function resolve(
  status: MarketStatus | null,
  source: 'rpc' | 'derived',
  nextOpen: Date | null,
  nextClose: Date | null,
  now: Date
): Pill {
  if (source === 'rpc' && status !== null && status !== MarketStatus.UNSPECIFIED) {
    switch (status) {
      case MarketStatus.OPEN:
        return { label: 'NYSE Open', dot: GREEN, tail: nextClose ? describeTarget(nextClose, 'closes', now) : '' };
      case MarketStatus.PRE_MARKET:
        return { label: 'Pre-Market', dot: ORANGE, tail: nextOpen ? describeTarget(nextOpen, 'opens', now) : '' };
      case MarketStatus.AFTER_HOURS:
        return { label: 'After Hours', dot: ORANGE, tail: nextOpen ? describeTarget(nextOpen, 'opens', now) : '' };
      default:
        return { label: 'NYSE Closed', dot: RED, tail: nextOpen ? describeTarget(nextOpen, 'opens', now) : '' };
    }
  }

  // Derived from the browser's ET wall clock (regular session only).
  const { hour, minute, isWeekday } = etParts(now);
  const mn = hour * 60 + minute;
  const openMin = 9 * 60 + 30;
  const closeMin = 16 * 60;
  if (isWeekday && mn >= openMin && mn < closeMin) {
    return { label: 'NYSE Open', dot: GREEN, tail: `closes ${fmtCountdown(closeMin - mn)}` };
  }
  if (isWeekday && mn < openMin) {
    return { label: 'NYSE Closed', dot: RED, tail: `opens ${fmtCountdown(openMin - mn)}` };
  }
  return { label: 'NYSE Closed', dot: RED, tail: '' };
}

export default function MarketStatusPill() {
  const { marketStatus, marketStatusSource, marketNextOpen, marketNextClose } = useDashboardStore();
  const [now, setNow] = useState(() => new Date());

  useEffect(() => {
    const id = setInterval(() => setNow(new Date()), 30_000);
    return () => clearInterval(id);
  }, []);

  const { hour, minute } = etParts(now);
  const etTime = `${hour}:${String(minute).padStart(2, '0')} ET`;
  const { label, dot, tail } = resolve(marketStatus, marketStatusSource, marketNextOpen, marketNextClose, now);
  const segments = [label, etTime, tail].filter(Boolean).join(' · ');

  return (
    <span
      className="inline-flex items-center gap-2 border-2 border-ink bg-paper px-3 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.08em]"
      title={marketStatusSource === 'rpc' ? 'Market clock from market-data service' : 'Market status derived from your browser clock (ET)'}
    >
      <span className="w-2 h-2" style={{ background: dot }} />
      {segments}
    </span>
  );
}
