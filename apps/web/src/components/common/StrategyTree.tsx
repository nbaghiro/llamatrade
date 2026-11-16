/**
 * StrategyTree draws a strategy as nested blocks with connectors and an optional build-up
 * animation. Used by the auth showcase, marketing and template previews. Pass `renderRow` to
 * layer interactivity. Colours come from tokens, so `ground` only remains for callers.
 */

import type { ReactNode } from 'react';

import { blockStyle, SELECTED_BLOCK } from '../strategy-builder/block-theme';

import {
  prepareForest,
  prepareTree,
  type BlockKind,
  type RawNode,
  type TreeNode,
} from './strategyTreeModel';

export type { BlockKind, RawNode, TreeNode } from './strategyTreeModel';

export type TreeGround = 'ink' | 'bone';

function kindStyle(kind: BlockKind) {
  return blockStyle(kind);
}

function AssetGlyph() {
  return (
    <span className="flex-none" aria-hidden="true">
      <svg
        width="15"
        height="15"
        viewBox="0 0 20 20"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.9}
      >
        <path d="M10 2 L18 6 L10 10 L2 6 Z" />
        <path d="M3 10 L10 13.5 L17 10" />
        <path d="M3 13.5 L10 17 L17 13.5" />
      </svg>
    </span>
  );
}

export interface StrategyBlockRowProps {
  node: Pick<TreeNode, 'kind' | 'kw' | 'label' | 'weight'>;
  ground?: TreeGround;
  /** Larger, full-width rows for the builder canvas; omit for the compact preview size. */
  comfortable?: boolean;
  selected?: boolean;
  /** Interactive controls placed before the keyword (e.g. delete/expand). */
  leading?: ReactNode;
  /** Interactive controls placed after the label (e.g. edit pencil). */
  trailing?: ReactNode;
  onClick?: (e: React.MouseEvent) => void;
  onDoubleClick?: (e: React.MouseEvent) => void;
  className?: string;
  testId?: string;
  /** Sets `data-symbol` — preserved for asset-row test/query hooks. */
  dataSymbol?: string;
}

/**
 * The rail-block row — the atomic visual shared by presentational and
 * interactive trees. Keep every strategy-block visual routed through here.
 */
export function StrategyBlockRow({
  node,
  ground: _ground = 'ink',
  comfortable = false,
  selected = false,
  leading,
  trailing,
  onClick,
  onDoubleClick,
  className = '',
  testId,
  dataSymbol,
}: StrategyBlockRowProps) {
  const style = kindStyle(node.kind);
  const sizeCls = comfortable
    ? 'min-h-[40px] w-full gap-2.5 px-3.5 py-1.5 text-[13px]'
    : 'min-h-[34px] gap-2 px-2.5 py-1 text-[12px]';
  const selectedRing = selected ? SELECTED_BLOCK : '';

  return (
    <div
      data-testid={testId}
      data-symbol={dataSymbol}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      className={`group relative flex items-center rounded-[4px] border border-line font-mono font-medium leading-[1.15] text-fg ${sizeCls} ${style.box} ${selectedRing} ${className}`}
    >
      {leading}
      {!node.kw && node.kind === 'asset' && <AssetGlyph />}
      {node.kw && <span className={`flex-none ${style.kw}`}>{node.kw}</span>}
      <span className="min-w-0 flex-1 truncate font-normal opacity-90">{node.label}</span>
      {node.weight && (
        <span
          className={`ml-auto flex-none rounded-[3px] bg-sunk px-1.5 leading-[1.5] tabular-nums text-fg ${comfortable ? 'text-[11px]' : 'text-[10px]'}`}
        >
          {node.weight}
        </span>
      )}
      {trailing}
    </div>
  );
}

/** Context handed to a custom `renderRow`, so callers can layer interactivity. */
export interface StrategyTreeRowContext {
  node: TreeNode;
  depth: number;
  visible: boolean;
  ground: TreeGround;
  /** The default presentational rail-block — return it as-is for read-only trees. */
  defaultRow: ReactNode;
}

interface BranchProps {
  node: TreeNode;
  depth: number;
  visibleCount: number;
  ground: TreeGround;
  comfortable: boolean;
  isRootLevel: boolean;
  renderRow?: (ctx: StrategyTreeRowContext) => ReactNode;
  renderAfterChildren?: (node: TreeNode, depth: number) => ReactNode;
}

function Branch({
  node,
  depth,
  visibleCount,
  ground,
  comfortable,
  isRootLevel,
  renderRow,
  renderAfterChildren,
}: BranchProps) {
  const visible = node.seq < visibleCount;
  const connector = 'border-line-strong';
  const elbowTop = comfortable ? 'top-[19px]' : 'top-[17px]';

  const defaultRow = <StrategyBlockRow node={node} ground={ground} comfortable={comfortable} />;
  const row = renderRow ? renderRow({ node, depth, visible, ground, defaultRow }) : defaultRow;

  const children = node.children ?? [];
  const after = renderAfterChildren?.(node, depth) ?? null;
  const showRegion = children.length > 0 || after !== null;

  return (
    <div className="relative">
      {!isRootLevel && (
        <span
          aria-hidden="true"
          className={`absolute left-[-16px] w-3.5 border-t ${elbowTop} ${connector}`}
          style={{ opacity: visible ? 1 : 0, transition: 'opacity .4s ease' }}
        />
      )}
      {/* Per-row reveal — each block fades/slides in on its own pre-order seq,
          giving the depth-first build animation. No-op when visibleCount = ∞. */}
      <div
        style={{
          opacity: visible ? 1 : 0,
          transform: visible ? 'translateX(0)' : 'translateX(-12px)',
          transition: 'opacity .45s ease, transform .45s cubic-bezier(.2,.8,.2,1)',
        }}
      >
        {row}
      </div>
      {showRegion && (
        <div
          className={`relative ml-2 border-l ${connector} pl-4`}
          style={{ opacity: visible ? 1 : 0, transition: 'opacity .4s ease' }}
        >
          {children.map((child) => (
            <div key={child.id} className="mt-1.5 first:mt-2">
              <Branch
                node={child}
                depth={depth + 1}
                visibleCount={visibleCount}
                ground={ground}
                comfortable={comfortable}
                isRootLevel={false}
                renderRow={renderRow}
                renderAfterChildren={renderAfterChildren}
              />
            </div>
          ))}
          {after}
        </div>
      )}
    </div>
  );
}

export interface StrategyTreeProps {
  /** Single prepared root (auth animation). */
  node?: TreeNode;
  /** Prepared forest — the builder renders the root's children as a forest. */
  nodes?: TreeNode[];
  /** Convenience: pass a raw single-root tree and it's prepared internally. */
  raw?: RawNode;
  /** Convenience: pass a raw forest and it's prepared internally. */
  rawForest?: RawNode[];
  /** Reveal only the first N pre-order blocks (build animation). Omit → all. */
  visibleCount?: number;
  /** Canvas the tree sits on: 'ink' (dark, default) or 'bone' (light). */
  ground?: TreeGround;
  /** Larger, full-width rows for the builder canvas; omit for the compact preview size. */
  comfortable?: boolean;
  className?: string;
  /** Override each row (the builder layers selection/expand/delete/edit here). */
  renderRow?: (ctx: StrategyTreeRowContext) => ReactNode;
  /** Rendered inside a parent's children block after the last child (e.g. add-block). */
  renderAfterChildren?: (node: TreeNode, depth: number) => ReactNode;
}

/**
 * StrategyTree — renders a prepared {@link TreeNode} (or forest) as the Monolith
 * block tree. Presentational by default; pass `renderRow` to make it interactive.
 */
export function StrategyTree({
  node,
  nodes,
  raw,
  rawForest,
  visibleCount,
  ground = 'ink',
  comfortable = false,
  className,
  renderRow,
  renderAfterChildren,
}: StrategyTreeProps) {
  const vc = visibleCount ?? Number.POSITIVE_INFINITY;

  const roots: TreeNode[] = nodes
    ? nodes
    : node
      ? [node]
      : rawForest
        ? prepareForest(rawForest).nodes
        : raw
          ? [prepareTree(raw).tree]
          : [];

  return (
    <div className={className}>
      {roots.map((root, i) => (
        <div key={root.id} className={i > 0 ? 'mt-2' : undefined}>
          <Branch
            node={root}
            depth={0}
            visibleCount={vc}
            ground={ground}
            comfortable={comfortable}
            isRootLevel
            renderRow={renderRow}
            renderAfterChildren={renderAfterChildren}
          />
        </div>
      ))}
    </div>
  );
}
