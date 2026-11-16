import { useAgentStore } from '@llamatrade/core/stores/agent';

import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { Pct } from '../../ui';

import type { EvidenceRun } from './evidence';
import type { Proposal } from './useProposal';

function Evidence({ runs }: { runs: readonly EvidenceRun[] }) {
  const rows: Array<[string, (r: EvidenceRun) => number | null, boolean]> = [
    ['Return', (r) => r.totalReturn, true],
    ['Max drawdown', (r) => r.maxDrawdown, true],
    ['Sharpe', (r) => r.sharpe, false],
  ];
  return (
    <table className="w-full border-collapse text-[12.5px]">
      <thead>
        <tr>
          <th className="py-1.5 text-left text-[11px] font-medium text-fg-3" />
          {runs.map((r, i) => (
            <th
              key={r.backtestId || i}
              className="py-1.5 text-right text-[11px] font-medium text-fg-3"
              title={r.backtestId}
            >
              Run {i + 1}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {rows.map(([label, pick, pct]) => (
          <tr key={label} className="border-t border-line">
            <td className="py-1.5 text-fg-2">{label}</td>
            {runs.map((r, i) => {
              const v = pick(r);
              return (
                <td key={r.backtestId || i} className="py-1.5 text-right">
                  {v === null ? (
                    <span className="text-fg-3">n/a</span>
                  ) : pct ? (
                    <Pct value={v} pnl dp={1} />
                  ) : (
                    <span className="num">{v.toFixed(2)}</span>
                  )}
                </td>
              );
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** The margin note beside a tracked change: what Copilot proposes, the runs behind it, and the choice. */
export function ProposalNote({ proposal }: { proposal: Proposal }) {
  const applyDSL = useStrategyBuilderStoreWithContext((s) => s.applyDSL);
  const strategyId = useStrategyBuilderStoreWithContext((s) => s.strategyId);
  const strategyName = useStrategyBuilderStoreWithContext((s) => s.strategyName);
  const setStrategyName = useStrategyBuilderStoreWithContext((s) => s.setStrategyName);
  const dismissArtifact = useAgentStore((s) => s.dismissArtifact);
  const openPanel = useAgentStore((s) => s.openPanel);
  const { diff, evidence, artifact } = proposal;

  const accept = () => {
    if (!applyDSL(proposal.dsl)) return;
    if (!strategyId && strategyName === 'New Strategy' && artifact.name)
      setStrategyName(artifact.name);
    dismissArtifact(artifact.id);
  };

  return (
    <aside
      aria-label="Copilot proposal"
      className="grid gap-2.5 rounded-panel border border-accent/50 bg-panel px-3.5 py-3 shadow-[0_0_0_3px_var(--accent-soft)]"
    >
      <b className="text-[13px] font-semibold">{artifact.name || 'Copilot proposes a change'}</b>
      {artifact.description && (
        <p className="m-0 text-[12.5px] text-fg-2">{artifact.description}</p>
      )}
      {diff.changes.length > 0 ? (
        <ul className="m-0 grid gap-1 pl-4 text-[12.5px] text-fg-2">
          {diff.changes.slice(0, 4).map((c) => (
            <li key={c}>{c}</li>
          ))}
          {diff.changes.length > 4 && <li>{diff.changes.length - 4} more changes</li>}
        </ul>
      ) : (
        <p className="m-0 text-[12.5px] text-fg-2">This matches the draft as it stands.</p>
      )}
      {evidence.length > 0 && (
        <>
          <span className="text-[12px] text-fg-3">
            Backtests Copilot read in this conversation:
          </span>
          <Evidence runs={evidence} />
        </>
      )}
      <div className="flex flex-wrap gap-1.5">
        <button type="button" onClick={accept} className="btn btn-primary btn-sm">
          Accept
        </button>
        <button
          type="button"
          onClick={() => dismissArtifact(artifact.id)}
          className="btn btn-secondary btn-sm"
        >
          Decline
        </button>
        <button type="button" onClick={openPanel} className="btn btn-ghost btn-sm">
          Reply
        </button>
      </div>
      <span className="text-[11.5px] text-fg-3">
        Nothing changes in the draft until you accept.
      </span>
    </aside>
  );
}
