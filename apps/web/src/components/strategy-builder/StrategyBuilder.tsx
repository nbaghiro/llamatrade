import { num } from '@llamatrade/core/format';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { toDSL } from '@llamatrade/core/strategy/serializer';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useStrategyBuilderStoreWithContext } from '../../store/strategy-builder';

import { CodeEditor } from './CodeEditor';
import { codeProblems } from './codemirror/problemModel';
import { CopilotAsk } from './copilot/CopilotAsk';
import { ProposalNote } from './copilot/ProposalNote';
import { useProposal } from './copilot/useProposal';
import { EditorHeader } from './EditorHeader';
import { useEngineCheck } from './hooks/useEngineCheck';
import { useRunningSession } from './hooks/useRunningSession';
import { BuilderOutline } from './outline/BuilderOutline';
import { EngineChip, PreviewRail } from './rail/PreviewRail';
import { SaveDialog } from './SaveDialog';

/** The editor: the outline or the code on the left, what it holds and needs on the right. */
export function StrategyBuilder() {
  const navigate = useNavigate();
  const store = useStrategyBuilderStoreWithContext();
  const {
    tree,
    viewMode,
    dslCode,
    timeframe,
    benchmark,
    strategyName,
    strategyDescription,
    strategyId,
    savedDsl,
    serverVersion,
    isDirty,
    ui,
    undo,
    redo,
    canUndo,
    canRedo,
    deleteBlock,
  } = store;
  const [saveOpen, setSaveOpen] = useState(false);

  const currentDsl = useMemo(
    () =>
      viewMode === 'code'
        ? dslCode
        : toDSL(tree, {
            name: strategyName,
            description: strategyDescription,
            timeframe,
            benchmark: benchmark || undefined,
          }),
    [viewMode, dslCode, tree, strategyName, strategyDescription, timeframe, benchmark]
  );
  const root = tree.blocks[tree.rootId];
  const hasRules = viewMode === 'code' || (root?.type === 'root' && root.childIds.length > 0);
  const engine = useEngineCheck(currentDsl, hasRules);
  const problems = useMemo(
    () =>
      engine.status === 'problems' && engine.errors && engine.checked === currentDsl
        ? codeProblems(currentDsl, engine.errors)
        : [],
    [engine, currentDsl]
  );

  const session = useRunningSession(strategyId);
  const proposal = useProposal();
  const showProposal = proposal !== null && viewMode !== 'code';

  const runs = useStrategiesStore((s) => s.runs);
  const fetchStrategyRun = useStrategiesStore((s) => s.fetchStrategyRun);
  useEffect(() => {
    if (strategyId) fetchStrategyRun(strategyId).catch(() => undefined);
  }, [strategyId, fetchStrategyRun]);
  const run = strategyId ? runs[strategyId] : null;
  const lastBacktest = run?.results?.metrics
    ? { version: run.strategyVersion, totalReturn: num(run.results.metrics.totalReturn) }
    : null;

  const onKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const target = e.target as HTMLElement | null;
      if (target?.closest('input, textarea, .cm-editor')) return;
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 'z' && !e.shiftKey) {
        e.preventDefault();
        if (canUndo()) undo();
      } else if (
        mod &&
        ((e.shiftKey && e.key.toLowerCase() === 'z') || e.key.toLowerCase() === 'y')
      ) {
        e.preventDefault();
        if (canRedo()) redo();
      } else if ((e.key === 'Backspace' || e.key === 'Delete') && ui.selectedBlockId) {
        const block = tree.blocks[ui.selectedBlockId];
        if (block && block.type !== 'root' && block.type !== 'else') {
          e.preventDefault();
          deleteBlock(ui.selectedBlockId);
        }
      }
    },
    [canUndo, canRedo, undo, redo, ui.selectedBlockId, tree, deleteBlock]
  );

  useEffect(() => {
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onKeyDown]);

  const hasSession = session.session !== null;

  return (
    <div className="page">
      <EditorHeader
        onSave={() => setSaveOpen(true)}
        onBacktest={() => strategyId && navigate(`/backtest?strategy=${strategyId}`)}
        sessionVersion={session.version}
        hasSession={hasSession}
        canSave={hasRules && (isDirty || !strategyId)}
      />

      <div className="grid items-start gap-8 lg:grid-cols-[minmax(0,1fr)_330px] lg:gap-9">
        <div className="min-w-0">
          {viewMode === 'code' ? (
            <section className="panel overflow-hidden">
              <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
                <b className="font-mono text-[12.5px] font-medium text-fg-2">
                  {(strategyName || 'strategy').toLowerCase().replace(/[^a-z0-9]+/g, '-')}.lt
                </b>
                <EngineChip engine={engine} />
              </header>
              <CodeEditor problems={problems} />
            </section>
          ) : (
            <>
              <CopilotAsk />
              <BuilderOutline tracked={showProposal ? proposal.diff : null} />
            </>
          )}
        </div>
        <div className="grid gap-4 lg:sticky lg:top-[72px]">
          {showProposal && <ProposalNote proposal={proposal} />}
          <PreviewRail
            tree={tree}
            timeframe={timeframe}
            benchmark={benchmark}
            engine={engine}
            savedDsl={savedDsl}
            savedVersion={serverVersion}
            session={session}
            lastBacktest={lastBacktest}
          />
        </div>
      </div>

      <SaveDialog
        open={saveOpen}
        onClose={() => setSaveOpen(false)}
        engine={engine}
        sessionVersion={session.version}
        hasSession={hasSession}
        onSaved={(id, thenBacktest) => {
          setSaveOpen(false);
          if (thenBacktest) navigate(`/backtest?strategy=${id}`);
          else navigate(`/strategies/${id}/edit`, { replace: true });
        }}
      />
    </div>
  );
}
