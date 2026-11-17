import { useAgentStore } from '@llamatrade/core/stores/agent';
import { Code2, Sparkles } from 'lucide-react';
import { useMemo } from 'react';

import { diffCode } from '../../../lib/strategyDiff';
import {
  UNTITLED_STRATEGY,
  useStrategyBuilderStoreWithContext,
} from '../../../store/strategy-builder';
import { Pct } from '../../ui';
import { RailPanel } from '../rail/RailPanel';

import type { EvidenceRun } from './evidence';
import { changedHunk } from './hunk';
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

function useAccept(proposal: Proposal) {
  const applyDSL = useStrategyBuilderStoreWithContext((s) => s.applyDSL);
  const strategyId = useStrategyBuilderStoreWithContext((s) => s.strategyId);
  const strategyName = useStrategyBuilderStoreWithContext((s) => s.strategyName);
  const setStrategyName = useStrategyBuilderStoreWithContext((s) => s.setStrategyName);
  const dismissArtifact = useAgentStore((s) => s.dismissArtifact);
  const { artifact } = proposal;
  return {
    accept: () => {
      if (!applyDSL(proposal.dsl)) return;
      if (!strategyId && strategyName === UNTITLED_STRATEGY && artifact.name)
        setStrategyName(artifact.name);
      dismissArtifact(artifact.id);
    },
    decline: () => dismissArtifact(artifact.id),
  };
}

/** copilot2 A: the proposal across the top, with the decision beside it. */
export function ProposalBanner({ proposal }: { proposal: Proposal }) {
  const { accept, decline } = useAccept(proposal);
  const openPanel = useAgentStore((s) => s.openPanel);
  const { artifact, diff } = proposal;
  return (
    <aside
      aria-label="Copilot proposal"
      className="mb-4 flex flex-col gap-3 rounded-panel border border-accent/50 bg-panel px-4 py-3.5 shadow-[0_0_0_3px_var(--accent-soft)] md:flex-row md:items-center md:gap-5"
    >
      <Sparkles className="hidden h-4 w-4 flex-none text-accent md:block" aria-hidden="true" />
      <p className="m-0 min-w-0 flex-1 text-[13.5px] text-fg-2">
        <b className="font-semibold text-fg">
          Copilot suggests {artifact.name ? artifact.name : 'a change'}.
        </b>{' '}
        {artifact.description}
        {diff.changes.length === 0 && ' This matches the draft as it stands.'}
      </p>
      <div className="flex flex-none flex-wrap gap-2">
        <button type="button" onClick={openPanel} className="btn btn-ghost">
          Reply
        </button>
        <button type="button" onClick={decline} className="btn btn-secondary">
          Decline
        </button>
        <button type="button" onClick={accept} className="btn btn-primary">
          Accept into the draft
        </button>
      </div>
    </aside>
  );
}

/** Beside the tracked outline: the exact code change and any backtests Copilot read. */
export function ProposalNote({ proposal, currentDsl }: { proposal: Proposal; currentDsl: string }) {
  const hunk = useMemo(
    () => changedHunk(diffCode(currentDsl, proposal.dsl)),
    [currentDsl, proposal.dsl]
  );
  const first = hunk.find((l) => l.kind !== 'same');
  const at = first?.newLine ?? first?.oldLine;
  const { diff, evidence } = proposal;
  return (
    <div className="grid gap-4">
      {diff.changes.length > 0 && (
        <RailPanel title="The change" meta={`${diff.changes.length} in words`}>
          <ul className="m-0 grid gap-1 pl-4 text-[12.5px] text-fg-2">
            {diff.changes.slice(0, 5).map((c) => (
              <li key={c}>{c}</li>
            ))}
            {diff.changes.length > 5 && <li>{diff.changes.length - 5} more changes</li>}
          </ul>
        </RailPanel>
      )}
      {hunk.length > 0 && (
        <section className="panel overflow-hidden">
          <header className="flex items-center gap-2 border-b border-line px-4 py-2.5 text-[12.5px] text-fg-2">
            <Code2 className="h-3.5 w-3.5 text-fg-3" aria-hidden="true" />
            {at ? `Line ${at} of the code` : 'The code'}
          </header>
          <pre className="m-0 overflow-x-auto py-2 font-mono text-[12px] leading-[1.7]">
            {hunk.map((l, i) => (
              <div
                key={i}
                className={`grid grid-cols-[28px_minmax(0,1fr)] gap-2 px-2 ${
                  l.kind === 'add'
                    ? 'bg-accent-soft shadow-[inset_2px_0_0_rgb(var(--accent))]'
                    : l.kind === 'del'
                      ? 'text-fg-3 line-through'
                      : ''
                }`}
              >
                <span className="select-none text-right text-fg-3">{l.newLine ?? ''}</span>
                <span className="whitespace-pre">
                  <span className="sr-only">
                    {l.kind === 'add' ? 'added ' : l.kind === 'del' ? 'removed ' : ''}
                  </span>
                  {l.text}
                </span>
              </div>
            ))}
          </pre>
        </section>
      )}
      {evidence.length > 0 && (
        <RailPanel title="Backtests Copilot read">
          <Evidence runs={evidence} />
        </RailPanel>
      )}
      <p className="m-0 text-[12px] leading-[1.55] text-fg-3">
        Accepting changes the draft only. A backtest of the change needs it saved as a version
        first, so its curve isn’t drawn here.
      </p>
    </div>
  );
}
