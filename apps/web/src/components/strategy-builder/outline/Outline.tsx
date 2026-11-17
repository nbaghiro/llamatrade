import { ChevronRight } from 'lucide-react';
import type { ReactNode } from 'react';

import {
  methodWords,
  partsText,
  type AssetShare,
  type OutlineLine,
  type OutlinePart,
} from '../../../lib/outline';
import type { DiffLine, DiffPart } from '../../../lib/strategyDiff';

import { HOLDING_FILLS } from './holdingFills';
import { Token, TrackedWas, type TokenEditHandler, type TokenOpenHandler } from './Token';

export type AnyLine = OutlineLine | DiffLine;
type AnyPart = OutlinePart | DiffPart;

const INDENT = 26;

export function Parts({
  parts,
  onEdit,
  onOpen,
  openKey,
}: {
  parts: readonly AnyPart[];
  onEdit?: TokenEditHandler;
  onOpen?: TokenOpenHandler;
  openKey?: string | null;
}) {
  return (
    <>
      {parts.map((p, i) =>
        p.kind === 'text' ? (
          <span key={i}>{p.text}</span>
        ) : (
          <Token key={i} token={p} onEdit={onEdit} onOpen={onOpen} openKey={openKey} />
        )
      )}
    </>
  );
}

function shareLabel(share: AssetShare | undefined): string {
  if (!share) return '';
  if (share.kind === 'fixed' || share.kind === 'equal') {
    return `${Math.round(share.pct * 10) / 10}%`;
  }
  if (share.kind === 'ranked') return `by ${methodWords(share.method)}`;
  if (share.kind === 'picked') {
    return share.pct === null ? 'if picked' : `${Math.round(share.pct * 10) / 10}% if picked`;
  }
  return '';
}

function ShareCell({
  line,
  fill,
  onEdit,
  onOpen,
}: {
  line: AnyLine;
  fill: string;
  onEdit?: TokenEditHandler;
  onOpen?: TokenOpenHandler;
}) {
  const share = line.share;
  const pct = share && (share.kind === 'fixed' || share.kind === 'equal') ? share.pct : null;
  const editable = line.parts.length > 0;
  return (
    <span className="grid grid-cols-[minmax(0,1fr)_auto] items-center gap-3 sm:grid-cols-[1fr_minmax(64px,auto)]">
      <span
        className={`hidden h-1.5 rounded-[1px] sm:block ${pct !== null ? 'bg-sunk' : ''}`}
        aria-hidden="true"
      >
        {pct !== null && (
          <i
            className="block h-full rounded-[1px]"
            style={{ width: `${Math.max(0, Math.min(100, pct))}%`, background: fill }}
          />
        )}
      </span>
      <span className="num whitespace-nowrap text-right text-[12.5px] text-fg">
        {editable ? (
          <Parts parts={line.parts} onEdit={onEdit} onOpen={onOpen} />
        ) : (
          <span className={pct === null ? 'font-sans text-fg-3' : ''}>{shareLabel(share)}</span>
        )}
      </span>
    </span>
  );
}

interface OutlineProps {
  lines: readonly AnyLine[];
  onEdit?: TokenEditHandler;
  /** Opens a rule folded past the visible depth. */
  onExpand?: (blockId: string) => void;
  selectedId?: string | null;
  onSelect?: (blockId: string) => void;
  /** Controls shown on hover at the end of a rule, e.g. add a holding or delete. */
  lineActions?: (line: AnyLine) => ReactNode;
  /** A sentence under a rule, e.g. weights that don't add to 100%. */
  notes?: ReadonlyMap<string, string>;
  /** Right-hand state per rule, e.g. "not applied". */
  aside?: (line: AnyLine) => ReactNode;
  dense?: boolean;
  label: string;
  /** Claims a token click before its popover opens, e.g. to open a larger editor under the rule. */
  onOpen?: TokenOpenHandler;
  /** `${blockId}:${field}` of the token whose larger editor is open, drawn as open. */
  openKey?: string | null;
  /** Content under a line, such as that larger editor. */
  below?: (line: AnyLine) => ReactNode;
}

/** The strategy as numbered sentences, with each holding's weight on its line. */
export function Outline({
  lines,
  onEdit,
  onExpand,
  selectedId,
  onSelect,
  lineActions,
  notes,
  aside,
  dense = false,
  label,
  onOpen,
  openKey,
  below,
}: OutlineProps) {
  let assetRun = 0;
  return (
    <ol aria-label={label} className="m-0 list-none border-t border-line p-0">
      {lines.map((line) => {
        const status = 'status' in line ? line.status : 'same';
        const isAsset = line.kind === 'asset';
        assetRun = isAsset ? assetRun + 1 : 0;
        const fill = HOLDING_FILLS[(assetRun - 1) % HOLDING_FILLS.length];
        const selected = selectedId === line.blockId && !isAsset;
        const removed = status === 'removed';
        const added = status === 'added';
        const pad = line.depth * INDENT + (isAsset ? INDENT : 0);
        const tone = removed
          ? 'text-fg-3'
          : selected
            ? 'bg-accent-soft shadow-[inset_2px_0_0_rgb(var(--accent))]'
            : added
              ? 'shadow-[inset_2px_0_0_rgb(var(--accent))]'
              : '';
        const note = notes?.get(line.blockId);

        if (line.kind === 'collapsed') {
          return (
            <li key={line.key} className="border-b border-line">
              <button
                type="button"
                onClick={() => onExpand?.(line.blockId)}
                className="grid w-full grid-cols-[22px_minmax(0,1fr)] items-center gap-2.5 py-2.5 text-left text-[13px] text-fg-2 hover:text-fg sm:grid-cols-[28px_minmax(0,1fr)] sm:gap-3.5"
              >
                <span />
                <span className="flex items-center gap-1.5" style={{ paddingLeft: pad }}>
                  <ChevronRight className="h-3.5 w-3.5" />
                  {partsText(line.parts)}
                </span>
              </button>
            </li>
          );
        }

        const body = isAsset ? (
          <span
            className="grid grid-cols-[52px_minmax(0,1fr)] items-baseline gap-2.5"
            style={{ paddingLeft: pad }}
          >
            <b className={`font-mono text-[12.5px] font-semibold ${removed ? 'line-through' : ''}`}>
              {line.symbol}
            </b>
            <span className="flex min-w-0 items-center gap-2">
              <span className="truncate text-fg-2">{line.name}</span>
              {lineActions && !removed && (
                <span className="flex gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
                  {lineActions(line)}
                </span>
              )}
            </span>
          </span>
        ) : (
          <span
            style={{ paddingLeft: pad }}
            className={removed ? 'line-through decoration-fg-3' : ''}
          >
            {'wasParts' in line && line.wasParts && (
              <>
                <TrackedWas>{partsText(line.wasParts)}</TrackedWas>{' '}
              </>
            )}
            <Parts
              parts={line.parts}
              onEdit={removed ? undefined : onEdit}
              onOpen={removed ? undefined : onOpen}
              openKey={openKey}
            />
          </span>
        );

        return (
          <li
            key={line.key}
            className={`group border-b border-line ${tone}`}
            aria-label={removed ? 'Removed' : added ? 'Added' : undefined}
            onClick={onSelect && !isAsset ? () => onSelect(line.blockId) : undefined}
          >
            <div
              className={`grid items-center gap-2.5 sm:gap-3.5 ${
                isAsset
                  ? 'grid-cols-[22px_minmax(0,1fr)_minmax(72px,auto)] py-[7px] text-[13px] sm:grid-cols-[28px_minmax(0,1fr)_minmax(190px,auto)]'
                  : `grid-cols-[22px_minmax(0,1fr)_auto] sm:grid-cols-[28px_minmax(0,1fr)_auto] ${dense ? 'py-2 text-[13.5px]' : 'py-3 text-[14px] sm:text-[15px]'}`
              } leading-normal`}
            >
              <span className="text-right font-mono text-[11.5px] text-fg-3 opacity-70">
                {line.number ?? ''}
              </span>
              {body}
              {isAsset ? (
                <ShareCell
                  line={line}
                  fill={fill}
                  onEdit={removed ? undefined : onEdit}
                  onOpen={removed ? undefined : onOpen}
                />
              ) : (
                <span className="flex items-center justify-end gap-1 text-right text-[12px] text-fg-3">
                  {aside?.(line)}
                  {lineActions && !removed && (
                    <span className="flex gap-1 opacity-100 transition-opacity sm:opacity-0 sm:group-focus-within:opacity-100 sm:group-hover:opacity-100">
                      {lineActions(line)}
                    </span>
                  )}
                </span>
              )}
            </div>
            {note && (
              <p className="m-0 pb-2.5 text-[12.5px] text-risk" style={{ paddingLeft: pad + 42 }}>
                {note}
              </p>
            )}
            {below?.(line)}
          </li>
        );
      })}
    </ol>
  );
}
