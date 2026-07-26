/**
 * StrategyTree — the single presentational renderer for the Monolith block/tree
 * editor visual. Used by EVERY strategy-tree render site:
 *  - the interactive builder (wraps rows with handlers via `renderRow`)
 *  - the auth "strategy builds itself" animation (`node` + `visibleCount`)
 *  - marketing, template previews, inline viewers, empty states
 *
 * It owns the recursive walk, the connectors, the reveal animation, and the
 * rail-block styling (`StrategyBlockRow`). It is ground-aware: pass
 * `ground="ink"` (default) for a dark canvas (auth/marketing) or `ground="bone"`
 * for the light builder canvas — this swaps neutral fills, connector, and ring
 * tints so the same rail-blocks read correctly on either surface.
 */

import type { ReactNode } from 'react';

import { prepareForest, prepareTree, type BlockKind, type RawNode, type TreeNode } from './strategyTreeModel';

export type { BlockKind, RawNode, TreeNode } from './strategyTreeModel';

export type TreeGround = 'ink' | 'bone';

interface KindStyle {
  box: string;
  kw: string;
}

/**
 * Per-kind rail-block styling. A 6px coloured left rail encodes the kind; the
 * fill is neutral (bone on an ink ground, paper on a bone ground) except the
 * `weight`/`else` theme tints and the orange `strategy`/`root` header.
 */
function kindStyle(kind: BlockKind, ground: TreeGround): KindStyle {
  const light = ground === 'bone';
  const surface = light ? 'bg-paper' : 'bg-bone';
  // Light builder canvas: every block carries a full 2px ink frame (the Split
  // Studio design). Dark auth ground: the offset shadow provides the edge.
  const frame = light ? 'border-2 border-ink ' : '';
  switch (kind) {
    case 'strategy':
    case 'root':
      return { box: `${frame}bg-orange-500 text-ink border-l-[5px] border-l-ink`, kw: 'text-ink' };
    case 'if':
    case 'filter':
      // Solid theme-orange conditional gate on the light builder canvas; light
      // surface + orange rail on the dark auth ground.
      return light
        ? { box: `${frame}bg-orange-500 text-ink border-l-[5px] border-l-ink`, kw: 'text-ink' }
        : { box: `${surface} text-ink border-l-[5px] border-l-orange-500`, kw: 'text-orange-600' };
    case 'weight':
      // Solid deep green on the light builder canvas (the pale tint read washed
      // out); keep the light tint on the dark auth ground where it pops.
      return light
        ? { box: `${frame}bg-green-600 text-bone border-l-[5px] border-l-green-800`, kw: 'text-bone' }
        : { box: `bg-block-weight text-ink border-l-[5px] border-l-green-600`, kw: 'text-green-700' };
    case 'else':
      // Solid warm near-black with an orange rail (pairs it with its IF) on the
      // light builder canvas; keep the warm tint on the dark auth ground.
      return light
        ? { box: `${frame}bg-gray-900 text-bone border-l-[5px] border-l-orange-500`, kw: 'text-bone' }
        : { box: `bg-block-else text-ink border-l-[5px] border-l-ink`, kw: 'text-ink' };
    case 'group':
      return { box: `${frame}${surface} text-ink border-l-[5px] border-l-ink`, kw: 'text-ink' };
    case 'asset':
      return { box: `${frame}bg-paper text-ink border-l-[5px] border-l-blue-600`, kw: light ? 'text-blue-600' : '' };
  }
}

function AssetGlyph() {
  return (
    <span className="flex-none" aria-hidden="true">
      <svg width="15" height="15" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.9}>
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
  ground = 'ink',
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
  const light = ground === 'bone';
  const style = kindStyle(node.kind, ground);
  const ringOffset = light ? 'ring-offset-bone' : 'ring-offset-ink';
  // Colour theme follows `ground`; size follows `comfortable` (builder = large,
  // full-width; preview/auth = compact). Light ground carries a full ink frame;
  // the dark ground leans on the offset shadow for its edge.
  const shadow = light ? '' : 'shadow-block';
  const sizeCls = comfortable
    ? 'min-h-[40px] w-full gap-2.5 px-3.5 py-1.5 text-[13px]'
    : 'min-h-[34px] gap-2 px-2.5 py-1 text-[12px]';
  const badgeCls = light ? 'bg-ink text-bone' : 'bg-orange-500 text-ink';
  const selectedRing = selected ? `ring-2 ring-orange-500 ring-offset-2 ${ringOffset}` : '';

  return (
    <div
      data-testid={testId}
      data-symbol={dataSymbol}
      onClick={onClick}
      onDoubleClick={onDoubleClick}
      className={`group relative flex items-center font-mono font-bold leading-[1.15] ${sizeCls} ${shadow} ${style.box} ${selectedRing} ${className}`}
    >
      {leading}
      {!node.kw && node.kind === 'asset' && <AssetGlyph />}
      {node.kw && <span className={`flex-none ${style.kw}`}>{node.kw}</span>}
      <span className="min-w-0 flex-1 truncate font-normal opacity-90">{node.label}</span>
      {node.weight && (
        <span className={`ml-auto flex-none border-2 border-ink px-1.5 leading-[1.5] tabular-nums ${comfortable ? 'text-[11px]' : 'text-[10px]'} ${badgeCls}`}>
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
  const connector = ground === 'ink' ? 'border-bone/25' : 'border-ink/25';
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
          className={`absolute left-[-16px] w-3.5 border-t-2 ${elbowTop} ${connector}`}
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
          className={`relative ml-2 border-l-2 ${connector} pl-4`}
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
