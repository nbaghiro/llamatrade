/**
 * StrategyTree — a presentational, prop-driven renderer for the Monolith
 * block/tree editor visual (the "strategy builds itself" node tree).
 *
 * It is purely presentational: callers supply the data (a {@link TreeNode})
 * and, optionally, a `visibleCount` to drive a pre-order build animation
 * (reveal the first N blocks). Omit `visibleCount` to render fully composed.
 *
 * Designed to sit on an ink (dark) ground — connectors and block shadows use
 * bone-tinted colors. Wrap it in a `bg-ink` container (see AuthShowcase / the
 * marketing hero).
 */

import type { BlockKind, TreeNode } from './strategyTreeModel';

export type { BlockKind, RawNode, TreeNode } from './strategyTreeModel';

/**
 * Per-kind block styling. Blocks sit on an ink ground; fills provide the shape.
 *
 * The two block-only fills (`else`, `weight`) come from the theme token layer
 * (`--lt-block-*-bg` in `themes/monolith.css`); every other color is a preset
 * token class (`bg-orange-500`, `border-l-blue-600`, …). So the whole tree
 * reskins purely from the theme file.
 */
const KIND_STYLES: Record<BlockKind, { box: string; kw: string }> = {
  strategy: { box: 'bg-orange-500 text-ink', kw: 'text-ink' },
  if: { box: 'bg-bone text-ink border-l-[6px] border-l-orange-500', kw: 'text-orange-600' },
  filter: { box: 'bg-bone text-ink border-l-[6px] border-l-orange-500', kw: 'text-orange-600' },
  else: { box: 'bg-block-else text-ink border-l-[6px] border-l-ink', kw: 'text-ink' },
  weight: {
    box: 'bg-block-weight text-ink border-l-[6px] border-l-green-600',
    kw: 'text-green-700',
  },
  asset: { box: 'bg-paper text-ink border-l-[6px] border-l-blue-600', kw: '' },
};

function AssetGlyph() {
  return (
    <span className="flex-none" aria-hidden="true">
      {/* stroke follows the block's text color (ink on the `asset` block). */}
      <svg width="13" height="13" viewBox="0 0 20 20" fill="none" stroke="currentColor" strokeWidth={1.9}>
        <path d="M10 2 L18 6 L10 10 L2 6 Z" />
        <path d="M3 10 L10 13.5 L17 10" />
        <path d="M3 13.5 L10 17 L17 13.5" />
      </svg>
    </span>
  );
}

function BlockRow({ node, visible }: { node: TreeNode; visible: boolean }) {
  const style = KIND_STYLES[node.kind];
  return (
    <div
      className={`relative flex min-h-[34px] items-center gap-2 px-3 py-2 font-mono text-[11px] font-bold leading-tight shadow-block ${style.box}`}
      style={{
        opacity: visible ? 1 : 0,
        transform: visible ? 'translateX(0)' : 'translateX(-12px)',
        transition: 'opacity .45s ease, transform .45s cubic-bezier(.2,.8,.2,1)',
      }}
    >
      {node.kind === 'asset' && <AssetGlyph />}
      {node.kw && <span className={`flex-none ${style.kw}`}>{node.kw}</span>}
      <span className="min-w-0 flex-1 truncate">{node.label}</span>
      {node.weight && (
        <span className="flex-none border-2 border-ink bg-orange-500 px-1.5 py-0.5 text-[10px] text-ink">
          {node.weight}
        </span>
      )}
    </div>
  );
}

function Branch({
  node,
  visibleCount,
  root = false,
}: {
  node: TreeNode;
  visibleCount: number;
  root?: boolean;
}) {
  const visible = node.seq < visibleCount;
  return (
    <div className="relative">
      {!root && (
        <span
          aria-hidden="true"
          className="absolute left-[-20px] top-[16px] w-5 border-t-2 border-bone/25"
          style={{ opacity: visible ? 1 : 0, transition: 'opacity .4s ease' }}
        />
      )}
      <BlockRow node={node} visible={visible} />
      {node.children && node.children.length > 0 && (
        <div
          className="relative ml-2 border-l-2 border-bone/25 pl-5"
          style={{ opacity: visible ? 1 : 0, transition: 'opacity .4s ease' }}
        >
          {node.children.map((child) => (
            <div key={child.seq} className="mt-2 first:mt-3">
              <Branch node={child} visibleCount={visibleCount} />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export interface StrategyTreeProps {
  /** The strategy tree to render (with pre-order `seq` indices — see {@link prepareTree}). */
  node: TreeNode;
  /**
   * Reveal only the first N pre-order blocks (for the build animation).
   * Omit (or pass `undefined`) to render every block fully composed.
   */
  visibleCount?: number;
  /** Optional wrapper className. */
  className?: string;
}

/**
 * StrategyTree — renders a prepared {@link TreeNode} as the Monolith block tree.
 */
export function StrategyTree({ node, visibleCount, className }: StrategyTreeProps) {
  const vc = visibleCount ?? Number.POSITIVE_INFINITY;
  return (
    <div className={className}>
      <Branch node={node} visibleCount={vc} root />
    </div>
  );
}
