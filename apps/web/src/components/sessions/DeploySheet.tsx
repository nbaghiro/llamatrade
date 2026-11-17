import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { toDate } from '@llamatrade/core/stores/backtest';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { useDeployStore, validateDeploy } from '@llamatrade/core/stores/deploy';
import { useFundingStore } from '@llamatrade/core/stores/funding';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { useEffect, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { formatMoney } from '../../lib/format';
import { maskedKey } from '../../lib/scope';
import { DEFAULT_RISK_LIMITS } from '../../lib/sessionState';
import { KvList } from '../backtest/parts';
import { AnnotatedCurve, type CurveLane } from '../charts';
import { useSessionRows } from '../shell/useSessionRows';
import { ModeBadge } from '../ui/ModeBadge';
import { Sheet } from '../ui/Sheet';

import { dayLabel, etToday, rowNextRebalance } from './sessionRows';
import { etDayLabel, etHm, fillDays, nextRebalances } from './timeline';

export interface DeploySheetProps {
  open: boolean;
  onClose: () => void;
  strategyId: string;
  strategyName: string;
  /** 0 deploys the current version. */
  strategyVersion: number;
  /** Strategy.rebalance, e.g. "monthly". */
  rebalance?: string;
  /** Where the sheet was opened from, e.g. "from this backtest". */
  context?: string;
  /** Suggested capital, e.g. the backtest's starting capital. */
  suggestedCapital?: number;
}

const DAY_MS = 86_400_000;
const PERIOD: Record<string, string> = {
  daily: 'Each trading day',
  weekly: 'Each week after',
  monthly: 'Each month after',
  quarterly: 'Each quarter after',
  annually: 'Each year after',
};

/**
 * Starts a paper session for one strategy version, placed among the paper account's other
 * sessions on one time axis so it's clear when anything will happen (deploy2 A).
 */
export function DeploySheet({
  open,
  onClose,
  strategyId,
  strategyName,
  strategyVersion,
  rebalance,
  context = 'Alpaca paper',
  suggestedCapital,
}: DeploySheetProps) {
  const navigate = useNavigate();
  const resolveAccount = useFundingStore((s) => s.resolveAccount);
  const resolved = useFundingStore((s) => s.resolved);
  const resolving = useFundingStore((s) => s.resolving);
  const unallocated = useFundingStore((s) => s.unallocatedCash);
  const credentialId = useFundingStore((s) => s.paperCredentialId);
  const deploy = useDeployStore((s) => s.deploy);
  const deploying = useDeployStore((s) => s.deploying);
  const deployError = useDeployStore((s) => s.error);
  const clearError = useDeployStore((s) => s.clearError);
  const loaded = useTradingStore((s) => s.loaded);
  const loadBlotter = useTradingStore((s) => s.loadBlotter);
  const orders = useTradingStore((s) => s.orders);
  const credentials = useBrokerStore((s) => s.credentials);
  const rows = useSessionRows();
  const strategiesLoaded = useStrategiesStore((s) => s.strategies.length > 0);
  const fetchStrategies = useStrategiesStore((s) => s.fetchStrategies);
  const [draft, setDraft] = useState('');
  const [name, setName] = useState(strategyName);
  const [touched, setTouched] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    clearError();
    setTouched(false);
    setLiveError(null);
    setName(strategyName);
    resolveAccount().catch(() => undefined);
  }, [open, resolveAccount, clearError, strategyName]);

  useEffect(() => {
    if (!open) return;
    if (!loaded) loadBlotter().catch(() => undefined);
    if (!strategiesLoaded) fetchStrategies().catch(() => undefined);
  }, [open, loaded, loadBlotter, strategiesLoaded, fetchStrategies]);

  useEffect(() => {
    if (!open || !resolved) return;
    const start =
      suggestedCapital && suggestedCapital > 0
        ? Math.min(suggestedCapital, unallocated)
        : unallocated;
    setDraft(start > 0 ? String(Math.floor(start * 100) / 100) : '');
  }, [open, resolved, suggestedCapital, unallocated]);

  const amount = Number(draft);
  const invalid = resolved
    ? validateDeploy({
        allocation: amount,
        unallocatedCash: unallocated,
        hasPaperCredential: credentialId !== null,
      })
    : null;
  const noKeys = resolved && credentialId === null;
  const cred = credentials.find((c) => c.id === credentialId);
  const account = `Alpaca paper${cred ? ` ${maskedKey(cred.apiKeyPrefix)}` : ''}`;

  const now = new Date();
  const today = etToday(now);
  const planned = nextRebalances(rebalance ?? '', today, 2);
  const freq = (rebalance ?? '').trim().toLowerCase();
  const start = new Date(now.getTime() - 28 * DAY_MS);
  const futureEnd = new Date(
    Math.max(now.getTime() + 28 * DAY_MS, (planned[1]?.getTime() ?? 0) + 4 * DAY_MS)
  );
  const paper = rows.filter((r) => r.session.mode !== ExecutionMode.LIVE).slice(0, 6);
  const lanes: CurveLane[] = [
    ...paper.map((r): CurveLane => {
      const ended = r.view.open ? null : toDate(r.session.endedAt);
      const next = rowNextRebalance(r, today);
      return {
        id: r.session.id,
        label: r.name,
        tone: r.view.open ? 'default' : 'muted',
        spans: [
          {
            from: r.startedAt && r.startedAt > start ? r.startedAt : start,
            to: ended ?? undefined,
            style: r.view.open ? 'on' : 'off',
          },
        ],
        events: [
          ...fillDays(orders.filter((o) => o.sessionId === r.session.id))
            .filter((d) => d.at >= start)
            .map((d) => ({
              at: d.at,
              shape: 'ring' as const,
              title: etDayLabel(d.at),
            })),
          ...(ended ? [{ at: ended, shape: 'stop' as const }] : []),
        ],
        future: r.view.open
          ? { events: next ? [{ at: next, shape: 'planned' as const }] : [] }
          : { note: 'Stopped' },
      };
    }),
    {
      id: 'new',
      label: name.trim() || strategyName,
      badge: (
        <span className="text-[10px] font-semibold uppercase tracking-[0.06em] text-accent">
          New
        </span>
      ),
      spans: [{ from: now, style: 'off' }],
      events: [],
      future: {
        events: planned.map((at) => ({ at, shape: 'planned' as const })),
        note: planned.length ? undefined : 'Starts with the next market data',
      },
    },
  ];

  const onStart = async () => {
    setTouched(true);
    if (invalid) return;
    const result = await deploy({
      strategyId,
      strategyName,
      strategyVersion,
      allocation: amount,
      goLive: true,
      name: name.trim() ? `${name.trim()} (paper)` : undefined,
    });
    if (!result) return;
    if (result.liveError) {
      setLiveError(result.liveError);
      return;
    }
    onClose();
    navigate(result.sessionId ? `/trading/${result.sessionId}` : '/trading');
  };

  const chips = [
    ...(suggestedCapital && suggestedCapital > 0 && suggestedCapital <= unallocated
      ? [{ label: formatMoney(suggestedCapital, { dp: 0 }), v: suggestedCapital }]
      : []),
    ...(unallocated >= 10000 && suggestedCapital !== 10000 ? [{ label: '$10,000', v: 10000 }] : []),
    ...(unallocated > 0
      ? [{ label: 'All free cash', v: Math.floor(unallocated * 100) / 100 }]
      : []),
  ];

  return (
    <Sheet
      open={open}
      onClose={onClose}
      width={1120}
      title={
        <span className="grid gap-0.5">
          <span className="flex items-center gap-2">
            Deploy {strategyName}
            <ModeBadge mode="paper" size="sm" />
          </span>
          <span className="text-xs font-normal text-fg-3">
            {strategyVersion ? `Version ${strategyVersion}` : 'Current version'}
            {rebalance ? ` · rebalances ${rebalance.toLowerCase()}` : ''} · {context}
          </span>
        </span>
      }
      footer={
        <>
          <span className="mr-auto self-center text-[11.5px] text-fg-3">
            Simulated money. Orders fill against real quotes in Alpaca&apos;s paper engine.
          </span>
          <button type="button" className="btn btn-ghost" onClick={onClose}>
            Cancel
          </button>
          <button
            type="button"
            className="btn btn-primary"
            disabled={
              deploying ||
              !resolved ||
              noKeys ||
              Boolean(liveError) ||
              (touched && Boolean(invalid))
            }
            onClick={onStart}
          >
            {deploying ? 'Starting…' : 'Start paper session'}
          </button>
        </>
      }
    >
      <div className="grid gap-5 px-[18px] py-4 lg:grid-cols-[minmax(0,1fr)_340px]">
        <div className="grid min-w-0 content-start gap-4">
          <section className="rounded-panel border border-line px-4 pb-1 pt-3">
            <div className="text-[10.5px] font-medium uppercase tracking-[0.06em] text-fg-3">
              {account}
            </div>
            <b className="mb-2 block text-[13.5px] font-semibold">Where the new session sits</b>
            <AnnotatedCurve
              label="Paper sessions and the new one on one time axis"
              dates={[]}
              values={[]}
              start={start}
              end={now}
              height={6}
              labelWidth={180}
              futureWidth={260}
              now={{ label: `Now ${etHm(now)}` }}
              future={{ end: futureEnd, ticks: planned }}
              lanes={lanes}
              legend={[
                { shape: 'ring', label: 'Rebalance' },
                { shape: 'planned', label: 'Planned' },
              ]}
              tickFormat={dayLabel}
            />
          </section>
          <ol className="m-0 grid list-none gap-3 p-0 sm:grid-cols-3">
            <Step when="Today" title="The sleeve is funded">
              {amount > 0 ? formatMoney(amount, { dp: 0 }) : 'The capital'} moves from free cash
              into a {name.trim() || strategyName} sleeve. Nothing is bought yet.
            </Step>
            <Step when={planned[0] ? dayLabel(planned[0]) : 'Next rebalance'} title="First orders">
              The rules pick what to hold from the latest data and buy it with the sleeve&apos;s
              cash. Each order runs through the seven risk checks first.
            </Step>
            <Step when={PERIOD[freq] ?? 'After that'} title="One rebalance">
              {planned[1]
                ? `The next one runs on ${dayLabel(planned[1])}, the first trading day of its period.`
                : 'It rebalances on its schedule, and nothing trades in between.'}
            </Step>
          </ol>
        </div>

        <div className="grid content-start gap-4">
          {noKeys ? (
            <div
              role="alert"
              className="rounded-[8px] border border-risk-line bg-risk-soft px-3 py-2.5 text-[12.5px]"
            >
              <b className="block font-semibold text-risk">Alpaca paper isn&apos;t connected</b>
              Connect your paper keys in Settings, then deploy from here.{' '}
              <Link to="/settings/broker" className="text-accent hover:underline">
                Open Settings
              </Link>
            </div>
          ) : (
            <>
              <div className="grid gap-1.5">
                <span className="text-xs font-medium text-fg-2">Account</span>
                <div className="flex items-center justify-between gap-2 rounded-[8px] border border-dashed border-line-strong px-3 py-2 text-[12.5px]">
                  <span className="flex items-center gap-2">
                    <ModeBadge mode="paper" size="sm" />
                    {account}
                  </span>
                  <span className="num text-fg-3">
                    {resolving && !resolved ? '…' : `${formatMoney(unallocated)} free`}
                  </span>
                </div>
              </div>
              <label className="grid gap-1.5">
                <span className="text-xs font-medium text-fg-2">Capital</span>
                <span className="flex items-center gap-2 rounded-[10px] border border-line-strong px-3 py-2">
                  <span className="text-fg-3">$</span>
                  <input
                    type="number"
                    inputMode="decimal"
                    min={0}
                    step={100}
                    value={draft}
                    disabled={!resolved}
                    onChange={(e) => {
                      setDraft(e.target.value);
                      setTouched(true);
                    }}
                    aria-invalid={touched && Boolean(invalid)}
                    aria-describedby="deploy-capital-help"
                    className="num min-w-0 flex-1 bg-transparent text-[18px] font-semibold outline-none"
                  />
                </span>
                <span
                  id="deploy-capital-help"
                  className={`text-[11.5px] ${touched && invalid ? 'text-risk' : 'text-fg-3'}`}
                >
                  {resolving && !resolved
                    ? 'Reading your paper account…'
                    : touched && invalid
                      ? invalid
                      : `of ${formatMoney(unallocated)} free cash`}
                </span>
              </label>
              {chips.length > 0 && (
                <div className="-mt-2 flex flex-wrap gap-1.5">
                  {chips.map((c) => (
                    <button
                      key={c.label}
                      type="button"
                      onClick={() => {
                        setDraft(String(c.v));
                        setTouched(true);
                      }}
                      className={`rounded-full border px-3 py-1 text-[12px] ${
                        amount === c.v
                          ? 'border-accent bg-accent-soft'
                          : 'border-line hover:border-line-strong'
                      }`}
                    >
                      {c.label}
                    </button>
                  ))}
                </div>
              )}
            </>
          )}
          <label className="grid gap-1.5">
            <span className="text-xs font-medium text-fg-2">Name</span>
            <input
              className="input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={80}
            />
          </label>
          <div className="grid gap-1">
            <span className="text-xs font-medium text-fg-2">Limits on this account</span>
            <KvList
              rows={[
                ['Order value', formatMoney(DEFAULT_RISK_LIMITS.maxOrderValue, { dp: 0 })],
                ['Position size', formatMoney(DEFAULT_RISK_LIMITS.maxPositionSize, { dp: 0 })],
                ['Daily loss', formatMoney(DEFAULT_RISK_LIMITS.maxDailyLoss, { dp: 0 })],
                ['Order rate', `${DEFAULT_RISK_LIMITS.ordersPerMinute} a minute`],
              ]}
            />
            <p className="m-0 text-[11.5px] text-fg-3">
              These are the default limits. If your account has its own, those apply instead.
            </p>
          </div>
          {(deployError || liveError) && (
            <div
              role="alert"
              className="rounded-[8px] border border-risk-line bg-risk-soft px-3 py-2.5 text-[12.5px]"
            >
              {liveError ? (
                <>
                  <b className="block font-semibold text-risk">
                    The capital is set aside, but the session didn&apos;t start
                  </b>
                  {liveError}{' '}
                  <Link to="/trading" className="text-accent hover:underline" onClick={onClose}>
                    Open Sessions
                  </Link>
                </>
              ) : (
                <>
                  <b className="block font-semibold text-risk">The session couldn&apos;t start</b>
                  {deployError}
                </>
              )}
            </div>
          )}
        </div>
      </div>
    </Sheet>
  );
}

function Step({
  when,
  title,
  children,
}: {
  when: string;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <li className="rounded-panel border border-line px-4 py-3">
      <div className="font-mono text-[11.5px] text-fg-3">{when}</div>
      <b className="mt-1 block text-[13px] font-semibold">{title}</b>
      <p className="m-0 mt-1 text-[12.5px] text-fg-2">{children}</p>
    </li>
  );
}
