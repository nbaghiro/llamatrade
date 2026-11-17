import { toDSL } from '@llamatrade/core/strategy/serializer';
import { Code2 } from 'lucide-react';
import { useMemo } from 'react';

import { buildOutline, metaParts, methodWords, type OutlineLine } from '../../../lib/outline';
import { useStrategyBuilderStoreWithContext } from '../../../store/strategy-builder';
import { fileName } from '../code/cursorInfo';
import { EngineState } from '../code/EngineState';
import type { EngineCheck } from '../hooks/useEngineCheck';
import { Parts } from '../outline/Outline';
import type { TokenEditHandler } from '../outline/Token';
import { useTokenEdit } from '../outline/useTokenEdit';

import { codeTokens, splitRows, type CodeTokenKind } from './rows';

const TOKEN_CLASS: Record<CodeTokenKind, string> = {
  head: 'text-accent',
  keyword: 'text-fg-3',
  string: 'text-fg-2',
  number: 'font-medium text-fg',
  paren: 'text-fg-3',
  text: 'text-fg',
};

function CodeLines({ lines, from, to }: { lines: readonly string[]; from: number; to: number }) {
  if (to < from) return null;
  return (
    <pre className="m-0 overflow-x-auto py-2.5 font-mono text-[12.5px] leading-[1.75]">
      {lines.slice(from - 1, to).map((text, i) => (
        <div key={from + i} className="grid grid-cols-[40px_minmax(0,1fr)]">
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

/** Rules in words beside the code they become, one aligned row per rule (split2 A). */
export function SplitView({ engine }: { engine: EngineCheck }) {
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
        <EngineState engine={engine} />
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
