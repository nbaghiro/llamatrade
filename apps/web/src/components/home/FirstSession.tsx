import { CalendarDays, ChevronRight, LineChart, ShieldCheck, Scale, Sparkles } from 'lucide-react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { formatMoney, formatNumber, formatPct } from '../../lib/format';
import { copilotUrl } from '../../lib/palette';
import { RISK_CHECKS } from '../../lib/sessionState';
import { ModeBadge, StatusMark, WeightBar } from '../ui';

import type { Holding } from './holdings';
import { Chg } from './HomeHero';
import { dayLabel, etDay, type Fill, type HomeSession } from './homeModel';
import { HomePanel } from './HomePanels';
import { nextRebalance } from './lanes';

function Step({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <li className="flex gap-3 border-b border-line py-3 last:border-b-0">
      <span className="grid h-8 w-8 flex-none place-items-center rounded-full bg-accent-soft text-accent">
        {icon}
      </span>
      <div className="min-w-0">
        <div className="text-[13.5px] font-semibold text-fg">{title}</div>
        <div className="text-[12.5px] text-fg-2">{children}</div>
      </div>
    </li>
  );
}

const startedWords = (d: Date | null, today: Date) => {
  if (!d) return 'Running';
  const sameDay = etDay(d).getTime() === today.getTime();
  return sameDay
    ? `Running since ${d.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', hour12: false, timeZone: 'America/New_York' })}`
    : `Running since ${dayLabel(etDay(d))}`;
};

/** home/first-session B: while there is one young session, Home is about that session. */
export function FirstSession({
  session,
  holdings,
  cash,
  fills,
  rejected,
  today,
}: {
  session: HomeSession;
  holdings: readonly Holding[];
  cash: number | null;
  fills: readonly Fill[];
  rejected: number;
  today: Date;
}) {
  const sinceStart =
    session.value !== null && session.allocated ? session.value - session.allocated : null;
  const total = session.value ?? holdings.reduce((s, h) => s + h.value, 0) + (cash ?? 0);
  const next = session.state === 'running' ? nextRebalance(session.rebalance, today) : null;
  const orders = fills.length + rejected;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 lg:grid-cols-[minmax(0,1fr)_380px]">
      <section aria-label={session.name} className="panel-rim overflow-hidden">
        <div className="px-6 pb-5 pt-6">
          <div className="flex flex-wrap items-center gap-2.5">
            <Link
              to={session.href}
              className="text-[20px] font-semibold tracking-[-0.02em] hover:underline"
            >
              {session.name}
            </Link>
            <ModeBadge mode={session.mode} />
            <StatusMark
              className="ml-auto"
              state={session.view.mark}
              label={
                session.state === 'running' ? startedWords(session.startedAt, today) : undefined
              }
            />
          </div>
          <div className="mt-4 flex flex-wrap items-baseline gap-3.5">
            <span className="font-mono text-[40px] font-semibold leading-none tracking-[-0.04em]">
              {formatMoney(total)}
            </span>
            {sinceStart !== null && (
              <Chg value={sinceStart}>{formatMoney(sinceStart, { signed: true })} since start</Chg>
            )}
          </div>
        </div>
        {holdings.length === 0 ? (
          <p className="m-0 border-t border-line px-6 py-5 text-[13px] text-fg-2">
            No positions yet. The session places its first orders on its first bar while the market
            is open.
          </p>
        ) : (
          <div className="overflow-x-auto border-t border-line">
            <table className="w-full min-w-[560px] border-collapse text-[13px]">
              <thead>
                <tr className="text-left font-mono text-[10.5px] uppercase tracking-[0.06em] text-fg-3">
                  <th className="px-6 py-2.5 font-medium">Holding</th>
                  <th className="px-3 py-2.5 text-right font-medium">Target</th>
                  <th className="px-3 py-2.5 font-medium">Actual</th>
                  <th className="px-3 py-2.5 text-right font-medium">Shares</th>
                  <th className="px-3 py-2.5 text-right font-medium">Price</th>
                  <th className="px-6 py-2.5 text-right font-medium">Value</th>
                </tr>
              </thead>
              <tbody className="font-mono">
                {holdings.map((h) => {
                  const share = total > 0 ? h.value / total : 0;
                  return (
                    <tr key={h.symbol} className="border-t border-line">
                      <td className="px-6 py-2.5 font-semibold">{h.symbol}</td>
                      <td className="px-3 py-2.5 text-right text-fg-2">
                        {h.target === null ? '·' : formatPct(h.target, { dp: 0 })}
                      </td>
                      <td className="px-3 py-2.5">
                        <div className="flex items-center gap-2.5">
                          <WeightBar
                            weight={share}
                            target={h.target ?? undefined}
                            className="w-24"
                            label={`${h.symbol} weight`}
                          />
                          {formatPct(share, { dp: 1 })}
                        </div>
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        {formatNumber(h.shares, { dp: h.shares % 1 ? 2 : 0 })}
                      </td>
                      <td className="px-3 py-2.5 text-right">
                        {h.price === null ? '·' : formatMoney(h.price)}
                      </td>
                      <td className="px-6 py-2.5 text-right">{formatMoney(h.value)}</td>
                    </tr>
                  );
                })}
                {cash !== null && (
                  <tr className="border-t border-line">
                    <td className="px-6 py-2.5 font-sans text-fg-2">Cash</td>
                    <td className="px-3 py-2.5 text-right text-fg-3">·</td>
                    <td className="px-3 py-2.5">
                      {total > 0 ? formatPct(cash / total, { dp: 1 }) : '·'}
                    </td>
                    <td className="px-3 py-2.5 text-right text-fg-3">·</td>
                    <td className="px-3 py-2.5 text-right text-fg-3">·</td>
                    <td className="px-6 py-2.5 text-right">{formatMoney(cash)}</td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        )}
        <div className="border-t border-line px-6 py-3.5 text-[12.5px] text-fg-3">
          Daily history starts at the close. After about a week, Home shows the account curve with
          this session&apos;s rebalances on it.
        </div>
      </section>

      <div className="grid content-start gap-4">
        <HomePanel title="What happens next">
          <ul className="m-0 list-none px-4 py-1">
            <Step
              icon={<CalendarDays className="h-4 w-4" />}
              title={
                next
                  ? `Rebalances on ${dayLabel(next)}`
                  : session.rebalance === 'Daily'
                    ? 'Rebalances each trading day'
                    : 'Rebalances on its schedule'
              }
            >
              {session.rebalance
                ? `${session.rebalance} schedule, back to the strategy's target weights.`
                : 'Back to the strategy’s target weights.'}
            </Step>
            <Step
              icon={<ShieldCheck className="h-4 w-4" />}
              title={`${RISK_CHECKS.length} checks on every order`}
            >
              {orders === 0
                ? 'No orders yet. Each one is checked before it reaches Alpaca.'
                : rejected === 0
                  ? `${orders === 1 ? 'The order so far' : `All ${orders} orders so far`} passed every check before reaching Alpaca.`
                  : `${fills.length} filled and ${rejected} ${rejected === 1 ? 'was' : 'were'} rejected. The session page shows why.`}
            </Step>
            <Step icon={<Scale className="h-4 w-4" />} title="Checked against Alpaca">
              The sleeve is compared with your Alpaca positions, and orders wait if they disagree.
            </Step>
          </ul>
        </HomePanel>
        <HomePanel title="While you wait">
          <div className="grid gap-2 p-4">
            <Link to="/strategies/templates" className="btn btn-secondary w-full justify-start">
              <LineChart aria-hidden="true" className="h-4 w-4" />
              Backtest another template
              <ChevronRight aria-hidden="true" className="ml-auto h-4 w-4" />
            </Link>
            <Link to={copilotUrl('')} className="btn btn-secondary w-full justify-start">
              <Sparkles aria-hidden="true" className="h-4 w-4" />
              Ask Copilot to draft a strategy
              <ChevronRight aria-hidden="true" className="ml-auto h-4 w-4" />
            </Link>
          </div>
        </HomePanel>
      </div>
    </div>
  );
}
