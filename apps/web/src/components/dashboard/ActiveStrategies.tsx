import {
  ExecutionStatus,
  useDashboardStore,
  type DashboardStrategy,
} from '@llamatrade/core/stores/dashboard';
import { Link } from 'react-router-dom';

import { Sparkline } from '../charts';
import { EmptyState, Money, Pct, StatusMark } from '../ui';

import { runStateOf } from './runState';

const HIDDEN: ReadonlySet<ExecutionStatus> = new Set([ExecutionStatus.STOPPED]);

function metaLine(s: DashboardStrategy): string {
  const positions = `${s.positionsCount} position${s.positionsCount === 1 ? '' : 's'}`;
  return [s.descriptor, positions].filter(Boolean).join(' · ');
}

function useRows() {
  const strategies = useDashboardStore((s) => s.strategies);
  const frozen = useDashboardStore((s) => s.frozenSleeves);
  const frozenIds = new Set((frozen ?? []).map((f) => f.executionId));
  return strategies
    .filter((s) => !HIDDEN.has(s.status))
    .map((s) => ({ strategy: s, state: runStateOf(s.status, frozenIds.has(s.id)) }));
}

/** The paper sessions on Home: allocation, return since start and state. */
export default function ActiveStrategies() {
  const rows = useRows();

  return (
    <section
      aria-label="Paper strategies"
      className="min-w-0 overflow-hidden rounded-panel border border-line bg-panel"
    >
      <div className="flex min-h-[42px] items-center justify-between gap-2.5 border-b border-line px-3.5 py-2.5 text-[12.5px]">
        <b className="font-semibold">Paper strategies</b>
        <Link to="/strategies" className="text-accent hover:underline">
          All strategies
        </Link>
      </div>
      {rows.length === 0 ? (
        <EmptyState
          title="No paper sessions running"
          body="Deploy a strategy to a paper session and it appears here with its allocation and return."
          actions={
            <Link to="/strategies" className="btn btn-secondary">
              Go to strategies
            </Link>
          }
        />
      ) : (
        <>
          <table className="hidden w-full border-collapse text-[12.5px] md:table">
            <thead>
              <tr className="text-left text-[11px] text-fg-3">
                <th className="border-b border-line px-3.5 py-2 font-medium">Strategy</th>
                <th className="w-px border-b border-line px-3.5 py-2 font-medium">Trend</th>
                <th className="w-px whitespace-nowrap border-b border-line px-3.5 py-2 text-right font-medium">
                  Allocated
                </th>
                <th className="w-px border-b border-line px-3.5 py-2 text-right font-medium">
                  Total
                </th>
                <th className="w-px border-b border-line px-3.5 py-2 font-medium">State</th>
              </tr>
            </thead>
            <tbody>
              {rows.map(({ strategy: s, state }) => (
                <tr key={s.id} className="[&:last-child>td]:border-b-0">
                  <td className="max-w-0 border-b border-line px-3.5 py-2 align-middle">
                    <Link
                      to={`/strategies/${encodeURIComponent(s.strategyId)}`}
                      className="block truncate font-semibold text-fg hover:underline"
                    >
                      {s.name}
                    </Link>
                    <span className="block truncate text-[11.5px] text-fg-3">{metaLine(s)}</span>
                  </td>
                  <td className="border-b border-line px-3.5 py-2">
                    <Sparkline
                      values={s.curve.map((p) => p.value)}
                      width={80}
                      height={22}
                      label={`${s.name} trend`}
                    />
                  </td>
                  <td className="whitespace-nowrap border-b border-line px-3.5 py-2 text-right">
                    <Money value={s.allocatedCapital} />
                  </td>
                  <td className="whitespace-nowrap border-b border-line px-3.5 py-2 text-right">
                    <Pct value={s.returns.ALL} pnl />
                  </td>
                  <td className="whitespace-nowrap border-b border-line px-3.5 py-2">
                    <StatusMark state={state} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <ul className="m-0 list-none px-4 py-0.5 md:hidden">
            {rows.map(({ strategy: s, state }) => (
              <li key={s.id} className="border-b border-line last:border-b-0">
                <Link
                  to={`/strategies/${encodeURIComponent(s.strategyId)}`}
                  className="flex items-center justify-between gap-3 py-3"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[14.5px] font-medium text-fg">
                      {s.name}
                    </span>
                    <span className="flex items-center gap-1.5 text-[12.5px] text-fg-3">
                      <StatusMark state={state} className="text-[12.5px]" />
                      {s.descriptor && <span>· {s.descriptor}</span>}
                    </span>
                  </span>
                  <Pct value={s.returns.ALL} pnl className="text-[14px]" />
                </Link>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}
