import { toDSL } from '@llamatrade/core/strategy/serializer';
import { Code2 } from 'lucide-react';
import { useMemo } from 'react';

import { buildOutline, metaParts, methodWords, type OutlineLine } from '../../../lib/outline';
import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { useMediaQuery } from '../../strategies/useMediaQuery';
import { fileName } from '../code/cursorInfo';
import { EngineState } from '../code/EngineState';
import type { EngineCheck } from '../hooks/useEngineCheck';
import { Parts } from '../outline/Outline';
import type { TokenEditHandler } from '../outline/Token';
import { useTokenEdit } from '../outline/useTokenEdit';

import { codeTokens, splitRows, type CodeTokenKind } from './rows';
import { SplitHistoryStrip, type SplitHistory } from './SplitHistoryStrip';

const TOKEN_CLASS: Record<CodeTokenKind, string> = {
  head: 'text-accent',
  keyword: 'text-fg-3',
  string: 'text-fg-2',
  number: 'font-medium text-fg',
  paren: 'text-fg-3',
  text: 'text-fg',
};

function CodeLines({
  lines,
  from,
  to,
  lit,
}: {
  lines: readonly string[];
  from: number;
  to: number;
  /** Lines drawn as selected. */
  lit?: { from: number; to: number } | null;
}) {
  if (to < from) return null;
  return (
    <pre className="m-0 overflow-x-auto py-2.5 font-mono text-[12.5px] leading-[1.75]">
      {lines.slice(from - 1, to).map((text, i) => (
        <div
          key={from + i}
          className={`grid grid-cols-[40px_minmax(0,1fr)] ${
            lit && from + i >= lit.from && from + i <= lit.to
              ? 'bg-accent-soft shadow-[inset_2px_0_0_rgb(var(--accent))]'
              : ''
          }`}
        >
          <span className="select-none pr-3 text-right text-fg-3 opacity-70">{from + i}</span>
          <code className="whitespace-pre">
            {codeTokens(text).map((t, j) => (
              <span key={j} className={TOKEN_CLASS[t.kind]}>
                {t.text}
              </span>
            ))}
          </code>
        </div>
      ))}
    </pre>
  );
}

function shareText(line: OutlineLine): string {
  const share = line.share;
  if (!share) return '';
  if (share.kind === 'equal') return `${Math.round(share.pct * 10) / 10}%`;
  if (share.kind === 'ranked') return `by ${methodWords(share.method)}`;
  if (share.kind === 'picked') return 'if picked';
  return '';
}

function WordLine({ line, onEdit }: { line: OutlineLine; onEdit: TokenEditHandler }) {
  if (line.kind === 'asset') {
    return (
      <div
        className="grid grid-cols-[52px_minmax(0,1fr)_auto] items-baseline gap-2.5 py-[3px] text-[13px]"
        style={{ paddingLeft: 28 + line.depth * 18 }}
      >
        <b className="font-mono text-[12.5px] font-semibold">{line.symbol}</b>
        <span className="truncate text-fg-2">{line.name}</span>
        <span className="num text-right text-[12.5px]">
          {line.parts.length > 0 ? (
            <Parts parts={line.parts} onEdit={onEdit} />
          ) : (
            <span className="font-sans text-fg-3">{shareText(line)}</span>
          )}
        </span>
      </div>
    );
  }
  return (
    <div className="grid grid-cols-[22px_minmax(0,1fr)] items-baseline gap-1.5 py-1 text-[14px] leading-normal">
      <span className="text-right font-mono text-[11.5px] text-fg-3 opacity-70">
        {line.number ?? ''}
      </span>
      <span style={{ paddingLeft: line.depth * 18 }}>
        <Parts parts={line.parts} onEdit={onEdit} />
      </span>
    </div>
  );
}

interface SplitViewProps {
  engine: EngineCheck;
  counts?: { errors: number; warnings: number };
  /** The saved version's last backtest, for the side-held pane on wide screens. */
  history: SplitHistory | null;
}

/**
 * Rules in words beside the code they become. On wide screens, three panes (split2 C):
 * compact rules, the code, and when each side held; otherwise one aligned row per rule.
 */
export function SplitView({ engine, counts, history }: SplitViewProps) {
  const wide = useMediaQuery('(min-width: 1280px)');
  const store = useStrategyBuilderStoreWithContext();
  const { tree, timeframe, benchmark, strategyName, strategyDescription, ui } = store;
  const onEdit = useTokenEdit();

  const code = useMemo(
    () =>
      toDSL(tree, {
        name: strategyName,
        description: strategyDescription,
        timeframe,
        benchmark: benchmark || undefined,
      }),
    [tree, strategyName, strategyDescription, timeframe, benchmark]
  );
  const codeLines = useMemo(() => code.split('\n'), [code]);
  const rows = useMemo(() => splitRows(tree, code), [tree, code]);
  const meta = useMemo(() => metaParts({ timeframe, benchmark }), [timeframe, benchmark]);
  const selected = ui.selectedBlockId;

  const header = (
    <div className="grid border-b border-line lg:grid-cols-2">
      <div className="flex items-center justify-between gap-3 px-4 py-2.5">
        <h3 className="m-0 text-[13px] font-semibold text-fg">Rules</h3>
        <EngineState engine={engine} counts={counts} />
      </div>
      <div className="hidden items-center gap-2 border-l border-line px-4 py-2.5 lg:flex">
        <Code2 className="h-4 w-4 text-fg-3" aria-hidden="true" />
        <b className="font-mono text-[12.5px] font-medium text-fg-2">{fileName(strategyName)}</b>
      </div>
    </div>
  );

  const settingsWords = (
    <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1">
      <span className="kicker w-[86px] flex-none">Settings</span>
      <span className="text-[13.5px] text-fg-2">
        <Parts parts={meta} onEdit={onEdit} />
      </span>
    </div>
  );

  if (wide) {
    const selectedRow =
      rows?.find((r) => r.kind === 'rule' && selected !== null && r.blockIds.includes(selected)) ??
      null;
    return (
      <div className="grid items-start gap-5 grid-cols-[minmax(0,0.85fr)_minmax(0,1.05fr)_minmax(280px,0.8fr)]">
        <section className="panel min-w-0 overflow-hidden" aria-label="Rules">
          <header className="border-b border-line px-4 py-2.5">
            <h3 className="m-0 text-[13px] font-semibold text-fg">Rules</h3>
          </header>
          <div className="grid gap-1 px-2 py-3">
            <div className="px-2 pb-1">{settingsWords}</div>
            {rows
              ? rows
                  .filter((r) => r.kind === 'rule')
                  .map((row) => {
                    const on = row === selectedRow;
                    return (
                      <div
                        key={row.key}
                        onClick={() => store.selectBlock(on ? null : row.blockIds[0])}
                        className={`cursor-pointer rounded-[8px] border px-2 py-1 ${
                          on
                            ? 'border-accent/45 bg-accent-soft'
                            : 'border-transparent hover:bg-sunk/60'
                        }`}
                      >
                        {row.lines.map((l) => (
                          <WordLine key={l.key} line={l} onEdit={onEdit} />
                        ))}
                      </div>
                    );
                  })
              : buildOutline(tree).map((l) => <WordLine key={l.key} line={l} onEdit={onEdit} />)}
          </div>
        </section>
        <section className="panel min-w-0 overflow-hidden" aria-label="Code">
          <header className="flex items-center justify-between gap-3 border-b border-line px-4 py-2.5">
            <span className="flex min-w-0 items-center gap-2">
              <Code2 className="h-4 w-4 flex-none text-fg-3" aria-hidden="true" />
              <b className="truncate font-mono text-[12.5px] font-medium text-fg-2">
                {fileName(strategyName)}
              </b>
            </span>
            <EngineState engine={engine} counts={counts} />
          </header>
          <CodeLines
            lines={codeLines}
            from={1}
            to={codeLines.length}
            lit={selectedRow ? selectedRow.code : null}
          />
          {!rows && (
            <p className="m-0 border-t border-line px-4 py-2 text-[12px] text-fg-3">
              Selection lines up again once the code and the rules match.
            </p>
          )}
        </section>
        {history ? (
          <SplitHistoryStrip {...history} />
        ) : (
          <section className="panel min-w-0" aria-label="When each side held">
            <header className="border-b border-line px-4 py-2.5">
              <h3 className="m-0 text-[13px] font-semibold text-fg">When each side held</h3>
            </header>
            <p className="m-0 px-4 py-4 text-[12.5px] leading-[1.55] text-fg-2">
              No backtest of the saved version yet. Once there is one, this shows which side of each
              rule held at every rebalance.
            </p>
          </section>
        )}
      </div>
    );
  }

  if (!rows) {
    return (
      <div>
        <section className="panel overflow-hidden">
          {header}
          <div className="grid lg:grid-cols-2">
            <div className="grid gap-1 px-4 py-3">
              {settingsWords}
              {buildOutline(tree).map((l) => (
                <WordLine key={l.key} line={l} onEdit={onEdit} />
              ))}
            </div>
            <div className="border-t border-line bg-sunk/40 lg:border-l lg:border-t-0">
              <CodeLines lines={codeLines} from={1} to={codeLines.length} />
            </div>
          </div>
        </section>
        <p className="m-0 mt-2.5 text-[12px] text-fg-3">
          The two sides line up again once the code and the rules match.
        </p>
      </div>
    );
  }

  return (
    <div>
      <section className="panel overflow-hidden" aria-label="Rules beside their code">
        {header}
        {rows.map((row) => {
          const on =
            row.kind === 'rule' ? selected !== null && row.blockIds.includes(selected) : false;
          return (
            <div
              key={row.key}
              onClick={() => store.selectBlock(row.kind === 'rule' ? row.blockIds[0] : null)}
              className={`grid cursor-pointer border-b border-line last:border-b-0 lg:grid-cols-2 ${
                on ? 'bg-accent-soft shadow-[inset_2px_0_0_rgb(var(--accent))]' : ''
              }`}
            >
              <div className="px-4 py-3">
                {row.kind === 'settings'
                  ? settingsWords
                  : row.lines.map((l) => <WordLine key={l.key} line={l} onEdit={onEdit} />)}
              </div>
              <div
                className={`min-w-0 border-t border-dashed border-line lg:border-l lg:border-t-0 lg:border-solid ${
                  on ? '' : 'bg-sunk/40'
                }`}
              >
                <CodeLines lines={codeLines} from={row.code.from} to={row.code.to} />
              </div>
            </div>
          );
        })}
      </section>
      <p className="m-0 mt-2.5 text-[12px] text-fg-3">
        Click a row on either side to select it in both. Edits in words rewrite the code on the same
        row.
      </p>
    </div>
  );
}
