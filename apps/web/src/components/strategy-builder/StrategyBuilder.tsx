import { toNumber } from '@llamatrade/core/stores/backtest';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { fromDSLString, toDSL } from '@llamatrade/core/strategy/serializer';
import { useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { longDate } from '../../lib/backtestView';
import { formatMoney } from '../../lib/format';
import { metaParts, ruleNumbers, type OutlineToken } from '../../lib/outline';
import { diffStrategies, suggestNote, type StrategyDiff } from '../../lib/strategyDiff';
import {
  StrategyBuilderStoreContext,
  useStrategyBuilderStore,
  useStrategyBuilderStoreWithContext,
} from '../../store/strategy-builder';
import { useMediaQuery } from '../strategies/useMediaQuery';
import { WebOnlyNote } from '../ui';

import { useConditionFocus } from './blocks/useConditionFocus';
import { useWeightsFocus } from './blocks/useWeightsFocus';
import { CodeWorkspace } from './code/CodeWorkspace';
import { codeProblems } from './codemirror/problemModel';
import { CopilotAsk } from './copilot/CopilotAsk';
import { ProposalBanner, ProposalNote } from './copilot/ProposalNote';
import { useProposal } from './copilot/useProposal';
import { clearLocalDraft, writeLocalDraft } from './draft/localDraft';
import { EditorHeader, type HeaderBacktest } from './EditorHeader';
import { HandoffPanel } from './handoff/HandoffPanel';
import { useHandoffRun } from './handoff/useHandoffRun';
import { SideHistory } from './history/SideHistory';
import { useEngineCheck } from './hooks/useEngineCheck';
import { useRunningSession } from './hooks/useRunningSession';
import { BuilderOutline } from './outline/BuilderOutline';
import { Parts } from './outline/Outline';
import { tokenKey } from './outline/tokenKey';
import { useTokenEdit } from './outline/useTokenEdit';
import { PreviewRail } from './rail/PreviewRail';
import { SaveControl, type SaveWarning } from './save/SaveControl';
import { SavedPanel, type SavedInfo } from './save/SavedPanel';
import { SplitView } from './split/SplitView';
import { DraftQuestions } from './start/DraftQuestions';
import { StartRail } from './start/StartRail';
import { EmptyRulesHint, StartWays } from './start/StartWays';

type Focus = { kind: 'condition' | 'weights'; blockId: string; key: string } | null;

const CONDITION_FIELDS = /^cond\./;
const WEIGHT_FIELDS = new Set(['weight.method', 'weight.lookback', 'weight.top']);

/** The editor: blocks, code or both, with what the draft holds and needs beside it. */
export function StrategyBuilder() {
  const navigate = useNavigate();
  const store = useStrategyBuilderStoreWithContext();
  const scoped = useContext(StrategyBuilderStoreContext);
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
    saving,
    error,
    ui,
    validationResult,
    undo,
    redo,
    canUndo,
    canRedo,
    deleteBlock,
    saveStrategy,
  } = store;
  const phone = useMediaQuery('(max-width: 639px)');
  const onEdit = useTokenEdit();

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
  const ruleCount = root?.type === 'root' ? root.childIds.length : 0;
  const hasRules = viewMode === 'code' || ruleCount > 0;
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
  const run = strategyId ? (runs[strategyId] ?? null) : null;
  const lastBacktest = run?.results?.metrics
    ? { version: run.strategyVersion, totalReturn: toNumber(run.results.metrics.totalReturn) }
    : null;

  const nextVersion = strategyId ? serverVersion + 1 : 1;
  const sessionVersion = session.session ? (session.version ?? serverVersion) : null;

  // The saved version the draft is read against, and the one before it right after a save.
  const [saved, setSaved] = useState<SavedInfo | null>(null);
  const [previousDsl, setPreviousDsl] = useState<string | null>(null);
  useEffect(() => {
    if (isDirty) {
      setSaved(null);
      setPreviousDsl(null);
    }
  }, [isDirty]);
  const compareDsl = isDirty ? savedDsl : previousDsl;
  const compare: StrategyDiff | null = useMemo(() => {
    if (!compareDsl) return null;
    const parsed = fromDSLString(compareDsl);
    if (!parsed) return null;
    return diffStrategies(
      {
        tree: parsed.tree,
        meta: {
          timeframe: parsed.metadata.timeframe ?? '1D',
          benchmark: parsed.metadata.benchmark ?? '',
        },
      },
      { tree, meta: { timeframe, benchmark } }
    );
  }, [compareDsl, tree, timeframe, benchmark]);
  const savedTree = useMemo(
    () => (savedDsl ? (fromDSLString(savedDsl)?.tree ?? null) : null),
    [savedDsl]
  );

  const suggestedNote = useMemo(() => {
    if (!strategyId) return 'First version';
    return compare && isDirty ? suggestNote(compare) : '';
  }, [strategyId, compare, isDirty]);

  // Problems and warnings, in the validator's and the engine's own words.
  const numbers = useMemo(() => ruleNumbers(tree), [tree]);
  const errors = useMemo(() => {
    const out = validationResult.errors.map((e) => e.message);
    if (engine.status === 'problems' && engine.errors) {
      for (const e of engine.errors) out.push(`Line ${e.line}: ${e.message}`);
    }
    return out;
  }, [validationResult.errors, engine]);
  const warnings: SaveWarning[] = useMemo(
    () =>
      validationResult.warnings.map((w) => {
        const n = w.blockId ? numbers.get(w.blockId) : undefined;
        return { message: w.message, where: n ? `rule ${n}` : undefined };
      }),
    [validationResult.warnings, numbers]
  );

  // An untitled draft lives in this browser until version 1 is saved (start2 A).
  useEffect(() => {
    if (strategyId || !isDirty || ruleCount === 0) return;
    const t = setTimeout(() => writeLocalDraft({ dsl: currentDsl, name: strategyName }), 600);
    return () => clearTimeout(t);
  }, [strategyId, isDirty, ruleCount, currentDsl, strategyName]);

  const handoff = useHandoffRun();
  const [saveRequest, setSaveRequest] = useState(0);
  const sessionLine = session.session
    ? `The paper session keeps running version ${sessionVersion} until you switch it.`
    : 'Saving doesn’t trade or change any session.';

  const save = useCallback(
    async (note: string, thenBacktest = false) => {
      const before = savedDsl;
      const id = await saveStrategy(note || undefined);
      if (!id) return;
      clearLocalDraft();
      const savedVersion = (scoped ?? useStrategyBuilderStore).getState().serverVersion;
      setPreviousDsl(before);
      setSaved({
        version: savedVersion,
        note,
        noteWritten: note === suggestedNote,
        at: new Date(),
      });
      if (!strategyId) navigate(`/strategies/${id}/edit`, { replace: true });
      if (thenBacktest) handoff.start(id, savedVersion, run).catch(() => undefined);
    },
    [scoped, savedDsl, saveStrategy, suggestedNote, strategyId, navigate, handoff, run]
  );

  const canSave = hasRules && (isDirty || !strategyId) && engine.status !== 'checking';
  const blocked = errors.length > 0;

  const onKeyDown = useCallback(
    (e: KeyboardEvent) => {
      const mod = e.metaKey || e.ctrlKey;
      if (mod && e.key.toLowerCase() === 's') {
        e.preventDefault();
        if (!canSave || blocked || saving) return;
        if (warnings.length > 0) setSaveRequest((n) => n + 1);
        else save(suggestedNote).catch(() => undefined);
        return;
      }
      const target = e.target as HTMLElement | null;
      if (target?.closest('input, textarea, select, .cm-editor')) return;
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
    [
      canSave,
      blocked,
      saving,
      warnings.length,
      save,
      suggestedNote,
      canUndo,
      canRedo,
      undo,
      redo,
      ui.selectedBlockId,
      tree,
      deleteBlock,
    ]
  );
  useEffect(() => {
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [onKeyDown]);

  // A condition or weights editor opened from a value in the outline (condition2 A, weights2 A).
  const [focus, setFocus] = useState<Focus>(null);
  const closeFocus = useCallback(() => setFocus(null), []);
  useEffect(() => {
    if (focus && !tree.blocks[focus.blockId]) setFocus(null);
  }, [focus, tree]);
  const onOpen = useCallback(
    (token: OutlineToken) => {
      if (phone || !token.blockId) return false;
      const block = tree.blocks[token.blockId];
      if (!block) return false;
      let next: Focus = null;
      if (block.type === 'if' && CONDITION_FIELDS.test(token.field)) {
        next = { kind: 'condition', blockId: block.id, key: tokenKey(token) };
      } else if (block.type === 'weight' && WEIGHT_FIELDS.has(token.field)) {
        next = { kind: 'weights', blockId: block.id, key: tokenKey(token) };
      } else if (
        (block.type === 'asset' || block.type === 'group') &&
        token.field === 'asset.weight' &&
        block.parentId
      ) {
        const parent = tree.blocks[block.parentId];
        if (parent?.type === 'weight') {
          next = { kind: 'weights', blockId: parent.id, key: tokenKey(token) };
        }
      }
      if (!next) return false;
      setFocus((f) => (f?.blockId === next.blockId && f.kind === next.kind ? null : next));
      return true;
    },
    [phone, tree]
  );
  const conditionFocus = useConditionFocus(
    focus?.kind === 'condition' ? focus.blockId : null,
    closeFocus
  );
  const weightsFocus = useWeightsFocus(
    focus?.kind === 'weights' ? focus.blockId : null,
    closeFocus,
    {
      sessionEquity: session.session?.currentEquity
        ? toNumber(session.session.currentEquity)
        : null,
      savedDsl,
      savedVersion: serverVersion,
    }
  );
  const openFocus = conditionFocus ?? weightsFocus;

  const [describing, setDescribing] = useState<string | null>(null);
  const isEmptyDraft = !strategyId && ruleCount === 0 && viewMode === 'tree';

  // Header state.
  const changeCount = isDirty && compare ? compare.changes.length : 0;
  let chip: string;
  let meta: React.ReactNode;
  if (!strategyId) {
    chip = 'Draft';
    meta = 'Not saved yet. Kept in this browser until you save version 1.';
  } else if (isDirty) {
    chip = `v${nextVersion} draft`;
    meta = (
      <>
        <span className="mr-1 inline-block h-1.5 w-1.5 rounded-full bg-accent align-middle" />
        {changeCount > 0
          ? `${changeCount} ${changeCount === 1 ? 'change' : 'changes'}, not saved`
          : 'Not saved'}
        {sessionVersion !== null && ` · Version ${sessionVersion} runs in paper`}
        {warnings.length > 0 && (
          <span className="text-risk">
            {' '}
            · {warnings.length} {warnings.length === 1 ? 'warning' : 'warnings'}
          </span>
        )}
      </>
    );
  } else {
    chip = `v${serverVersion}`;
    meta = (
      <>
        {saved
          ? `Saved at ${saved.at.toLocaleTimeString('en-US', { hour: 'numeric', minute: '2-digit' })}`
          : 'Saved'}
        {sessionVersion !== null &&
          ` · Version ${sessionVersion} ${sessionVersion === serverVersion ? 'runs' : 'still runs'} in paper`}
      </>
    );
  }

  const baseVersion = run?.strategyVersion ?? null;
  const like = baseVersion ? ` like version ${baseVersion}` : '';
  const dirtyOrNew = isDirty || !strategyId;
  const backtest: HeaderBacktest | null = !hasRules
    ? null
    : {
        label: dirtyOrNew
          ? `Save version ${nextVersion} and backtest${like}`
          : `Backtest${baseVersion ? like : ` version ${serverVersion}`}`,
        disabled: handoff.phase === 'running' || saving || (dirtyOrNew && (!canSave || blocked)),
        title: blocked ? 'Fix the problems before saving.' : undefined,
        onRun: () => {
          if (dirtyOrNew) {
            if (warnings.length > 0) setSaveRequest((n) => n + 1);
            else save(suggestedNote, true).catch(() => undefined);
          } else if (strategyId) {
            handoff.start(strategyId, serverVersion, run).catch(() => undefined);
          }
        },
        settingsHref: strategyId ? `/backtest?strategy=${strategyId}` : null,
      };

  const backtestLine = useMemo(() => {
    const c = run?.config;
    const start = c?.startDate ? new Date(Number(c.startDate.seconds) * 1000) : null;
    const end = c?.endDate ? new Date(Number(c.endDate.seconds) * 1000) : null;
    if (!c || !start || !end) return 'Two years to today, $10,000, SPY. No earlier run to copy.';
    return `${longDate(start)} to ${longDate(end)}, ${formatMoney(toNumber(c.initialCapital), { dp: 0 })}${c.benchmarkSymbol ? `, ${c.benchmarkSymbol}` : ''}. Same as version ${run?.strategyVersion}’s last run.`;
  }, [run]);

  const header = (
    <EditorHeader
      chip={chip}
      chipTone={isDirty || !strategyId ? 'draft' : 'saved'}
      meta={meta}
      compact={phone}
      backtest={phone ? null : backtest}
      save={
        <SaveControl
          nextVersion={nextVersion}
          errors={hasRules ? errors : []}
          warnings={warnings}
          canSave={canSave}
          saving={saving}
          justSaved={!isDirty && saved !== null}
          suggestedNote={suggestedNote}
          sessionLine={sessionLine}
          onSave={(note) => save(note).catch(() => undefined)}
          openRequest={saveRequest}
        />
      }
    />
  );

  const errorLine = error && !saving && (
    <p role="alert" className="m-0 mb-3 text-[12.5px] text-loss">
      The version wasn’t saved. {error}
    </p>
  );

  if (describing !== null) {
    return (
      <div className="page max-w-[1400px]">
        {header}
        <DraftQuestions
          description={describing}
          onDone={() => setDescribing(null)}
          onCancel={() => setDescribing(null)}
        />
      </div>
    );
  }

  const afterRules = (
    <>
      {saved && !isDirty && !handoff.run && handoff.phase === 'idle' && (
        <SavedPanel
          saved={saved}
          backtestLine={backtestLine}
          onBacktest={() =>
            strategyId && handoff.start(strategyId, saved.version, run).catch(() => undefined)
          }
          onClose={() => setSaved(null)}
          session={
            session.session
              ? { id: session.session.id, name: session.session.name, version: sessionVersion }
              : null
          }
        />
      )}
      {handoff.phase !== 'idle' && strategyId && (
        <HandoffPanel
          state={handoff}
          version={handoff.run?.strategyVersion ?? serverVersion}
          onRetry={() =>
            handoff.start(strategyId, serverVersion, handoff.base).catch(() => undefined)
          }
          onClose={handoff.reset}
        />
      )}
    </>
  );

  if (viewMode === 'code' && !phone) {
    return (
      <div className="page max-w-[1400px]">
        {header}
        {errorLine}
        <CodeWorkspace engine={engine} problems={problems} warnings={validationResult.warnings} />
        <div className="mt-6 grid gap-6">{afterRules}</div>
      </div>
    );
  }

  if (viewMode === 'split' && !phone) {
    return (
      <div className="page max-w-[1400px]">
        {header}
        {errorLine}
        <SplitView engine={engine} />
        <div className="mt-6 grid gap-6">{afterRules}</div>
      </div>
    );
  }

  const metaLine = metaParts({ timeframe, benchmark });
  const rulesPanel = (
    <section className="panel overflow-visible">
      <header className="flex flex-wrap items-center justify-between gap-x-4 gap-y-1.5 border-b border-line px-5 py-3">
        <h3 className="m-0 text-[13.5px] font-semibold text-fg">Rules</h3>
        <span className="flex flex-wrap items-center gap-y-1 text-[12.5px] text-fg-2">
          {showProposal && proposal ? (
            <Parts parts={proposal.diff.meta} />
          ) : (
            <Parts
              parts={compare && compare.changes.length > 0 ? compare.meta : metaLine}
              onEdit={onEdit}
            />
          )}
        </span>
      </header>
      {isEmptyDraft ? (
        <>
          <StartWays
            blocks={!phone}
            onDescribe={setDescribing}
            onTemplate={(id) => navigate(`/strategies/builder?template=${encodeURIComponent(id)}`)}
          />
          <EmptyRulesHint />
        </>
      ) : (
        <div className="px-3 pb-3 pt-1 sm:px-5">
          <BuilderOutline
            hideMeta
            tracked={showProposal && proposal ? proposal.diff : null}
            compare={compare}
            structural={!phone}
            onOpen={onOpen}
            openKey={focus?.key ?? null}
            below={(line) =>
              openFocus && focus && line.blockId === focus.blockId ? (
                <div className="pb-3 pt-1">{openFocus.inline}</div>
              ) : null
            }
          />
          {!isDirty && previousDsl && compare && compare.changes.length > 0 && (
            <p className="m-0 pt-3 text-[12px] text-fg-3">
              Values struck through are version {serverVersion - 1}’s. The marks clear when you make
              your next change.
            </p>
          )}
        </div>
      )}
    </section>
  );

  const rail = isEmptyDraft ? (
    <StartRail />
  ) : openFocus ? (
    openFocus.rail
  ) : showProposal && proposal ? (
    <ProposalNote proposal={proposal} currentDsl={currentDsl} />
  ) : (
    <div className="grid gap-4">
      {!phone && <CopilotAsk />}
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
  );

  const selectedIf = ui.selectedBlockId ? tree.blocks[ui.selectedBlockId]?.type === 'if' : false;
  return (
    <div className="page max-w-[1400px]">
      {header}
      {errorLine}
      {phone && <WebOnlyNote what="Adding or removing rules" className="mb-4" />}
      {showProposal && proposal && <ProposalBanner proposal={proposal} />}
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_330px]">
        <div className="grid min-w-0 gap-6">
          {rulesPanel}
          {afterRules}
        </div>
        <div className="grid gap-4 lg:sticky lg:top-[72px]">{rail}</div>
      </div>
      {run && savedTree && !phone && !isEmptyDraft && (
        <div className="mt-6">
          <SideHistory run={run} tree={savedTree} lit={selectedIf || focus?.kind === 'condition'} />
        </div>
      )}
    </div>
  );
}
