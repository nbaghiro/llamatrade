import { useMemo, type KeyboardEvent, type ReactNode } from 'react';

import { methodWords, partsText, type OutlineLine } from '../../../lib/outline';
import { collapse, guidesOf, phraseParts, withKids } from '../../../lib/outlineTree';
import type { DiffLine } from '../../../lib/strategyDiff';
import { LiveMarker, Ticker, TreeBar, TreeRow, type TreeRowMark } from '../../ui';

import { Parts } from './Outline';
import { TrackedWas, type TokenEditHandler, type TokenOpenHandler } from './Token';

export type TreeLine = OutlineLine | DiffLine;

export const ROOT_ROW = 'strategy';

const TYPE: Record<OutlineLine['kind'], string> = {
  if: 'If',
  else: 'Else',
  weight: 'Weight',
  filter: 'Filter',
  group: 'Group',
  asset: 'Asset',
  collapsed: '',
};

const pctText = (pct: number) => `${Math.round(pct * 10) / 10}%`;

function lineMark(line: TreeLine): TreeRowMark | undefined {
  if (!('status' in line)) return undefined;
  return line.status === 'added' ? 'add' : line.status === 'removed' ? 'del' : undefined;
}

interface OutlineTreeProps {
  name: string;
  lines: readonly TreeLine[];
  /** Blocks on the path the running session holds today. */
  live: ReadonlySet<string>;
  closed: ReadonlySet<string>;
  onToggle: (id: string) => void;
  selectedId?: string | null;
  onSelect?: (blockId: string) => void;
  onEdit?: TokenEditHandler;
  onOpen?: TokenOpenHandler;
  openKey?: string | null;
  /** Controls shown on hover at the end of a row, e.g. add a holding or delete. */
  lineActions?: (line: TreeLine) => ReactNode;
  /** A sentence under a rule, e.g. weights that don't add to 100%. */
  notes?: ReadonlyMap<string, string>;
  /** Content under a row, such as a larger editor. */
  below?: (line: TreeLine) => ReactNode;
  label: string;
}

interface Row {
  id: string;
  depth: number;
  live: boolean;
  line: TreeLine | null;
}

/** The strategy as a tree: one row per block, guide lines to its parent, the held path in ink. */
export function OutlineTree({
  name,
  lines,
  live,
  closed,
  onToggle,
  selectedId,
  onSelect,
  onEdit,
  onOpen,
  openKey,
  lineActions,
  notes,
  below,
  label,
}: OutlineTreeProps) {
  const rows = useMemo(() => {
    const flat: Row[] = [
      { id: ROOT_ROW, depth: 0, live: live.size > 0, line: null },
      ...lines
        .filter((l) => l.kind !== 'collapsed')
        .map((l) => ({ id: l.key, depth: l.depth + 1, live: live.has(l.blockId), line: l })),
    ];
    const shown = collapse(withKids(flat), closed);
    const guides = guidesOf(shown);
    return shown.map((r, i) => ({ ...r, guides: guides[i] }));
  }, [lines, live, closed]);

  const selectable = rows.filter(
    (r) => r.line && r.line.kind !== 'asset' && lineMark(r.line) !== 'del'
  );
  const keys = (e: KeyboardEvent<HTMLDivElement>) => {
    if (!onSelect || (e.target as HTMLElement).closest('input, button, [role="dialog"]')) return;
    const i = selectable.findIndex((r) => r.line?.blockId === selectedId);
    const row = selectable[i];
    const go = (j: number) => {
      const next = selectable[j]?.line;
      if (next) onSelect(next.blockId);
    };
    if (e.key === 'ArrowDown') go(i + 1);
    else if (e.key === 'ArrowUp') go(i < 0 ? selectable.length - 1 : i - 1);
    else if (e.key === 'ArrowLeft' && row?.kids && !closed.has(row.id)) onToggle(row.id);
    else if (e.key === 'ArrowRight' && row?.kids && closed.has(row.id)) onToggle(row.id);
    else return;
    e.preventDefault();
  };

  return (
    <div
      role="tree"
      aria-label={label}
      tabIndex={onSelect ? 0 : undefined}
      onKeyDown={keys}
      className="py-2 outline-none"
    >
      {rows.map((r) => {
        const toggle = r.kids ? { closed: closed.has(r.id), onToggle: () => onToggle(r.id) } : {};
        if (!r.line) {
          return (
            <TreeRow
              key={r.id}
              role="treeitem"
              aria-level={1}
              guides={r.guides}
              type="Strategy"
              live={r.live}
              hiddenCount={r.hidden}
              {...toggle}
            >
              {name}
            </TreeRow>
          );
        }
        const line = r.line;
        const mark = lineMark(line);
        const removed = mark === 'del';
        const isAsset = line.kind === 'asset';
        const note = notes?.get(line.blockId);
        const under = below?.(line);
        const indent = 30 + r.depth * 22 + 26;
        return (
          <div key={r.id} className="group">
            <TreeRow
              role="treeitem"
              aria-level={r.depth + 1}
              aria-selected={selectedId === line.blockId && !isAsset}
              aria-label={removed ? `Removed: ${partsText(line.parts) || line.symbol}` : undefined}
              guides={r.guides}
              type={TYPE[line.kind]}
              live={r.live}
              mark={mark}
              flag={note ? 'warning' : undefined}
              selected={selectedId === line.blockId && !isAsset}
              hiddenCount={r.hidden}
              onClick={onSelect && !isAsset && !removed ? () => onSelect(line.blockId) : undefined}
              end={
                <RowEnd
                  line={line}
                  live={live}
                  removed={removed}
                  onEdit={removed ? undefined : onEdit}
                  onOpen={removed ? undefined : onOpen}
                  actions={lineActions && !removed ? lineActions(line) : null}
                />
              }
              {...toggle}
            >
              {isAsset ? (
                <>
                  <Ticker symbol={line.symbol ?? ''} />{' '}
                  {line.name && <span className="text-fg-3">{line.name}</span>}
                </>
              ) : (
                <>
                  {'wasParts' in line && line.wasParts && (
                    <>
                      <TrackedWas>
                        {partsText(phraseParts(line.kind, line.wasParts))}
                      </TrackedWas>{' '}
                    </>
                  )}
                  <Parts
                    parts={phraseParts(line.kind, line.parts)}
                    onEdit={removed ? undefined : onEdit}
                    onOpen={removed ? undefined : onOpen}
                    openKey={openKey}
                  />
                </>
              )}
            </TreeRow>
            {note && (
              <p className="m-0 pb-2 text-[12.5px] text-risk" style={{ paddingLeft: indent }}>
                {note}
              </p>
            )}
            {under && <div style={{ paddingLeft: indent }}>{under}</div>}
          </div>
        );
      })}
    </div>
  );
}

function RowEnd({
  line,
  live,
  removed,
  onEdit,
  onOpen,
  actions,
}: {
  line: TreeLine;
  live: ReadonlySet<string>;
  removed: boolean;
  onEdit?: TokenEditHandler;
  onOpen?: TokenOpenHandler;
  actions: ReactNode;
}) {
  const on = live.has(line.blockId);
  const hover = actions ? (
    <span className="flex gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
      {actions}
    </span>
  ) : null;
  if (line.kind === 'if' || line.kind === 'else') {
    return (
      <>
        {hover}
        {on && !removed && <LiveMarker />}
      </>
    );
  }
  if (line.kind !== 'asset') return hover;
  const share = line.share;
  const exact = share && (share.kind === 'fixed' || share.kind === 'equal') ? share.pct : null;
  const value =
    line.parts.length > 0 ? (
      <Parts parts={line.parts} onEdit={onEdit} onOpen={onOpen} />
    ) : exact !== null ? (
      pctText(exact)
    ) : share?.kind === 'picked' ? (
      share.pct === null ? (
        'If picked'
      ) : (
        `${pctText(share.pct)} if picked`
      )
    ) : share?.kind === 'ranked' ? (
      `By ${methodWords(share.method)}`
    ) : (
      ''
    );
  return (
    <>
      {hover}
      {exact !== null ? (
        <TreeBar pct={exact} live={on} muted={removed} />
      ) : share?.kind === 'picked' ? (
        <TreeBar pick live={on} />
      ) : null}
      <span
        className={`min-w-[46px] whitespace-nowrap text-right font-mono text-[12.5px] font-medium ${
          removed
            ? 'text-fg-3 line-through'
            : exact !== null
              ? 'text-fg'
              : 'font-sans font-normal text-fg-3'
        }`}
      >
        {value}
      </span>
    </>
  );
}
