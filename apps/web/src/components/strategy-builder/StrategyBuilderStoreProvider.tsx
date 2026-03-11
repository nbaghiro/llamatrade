/**
 * Scoped store provider for strategy builder.
 *
 * Allows rendering strategy visualizations with isolated state,
 * useful for inline previews in chat messages or modals.
 */

import { useMemo } from 'react';

import {
  createStrategyBuilderStore,
  StrategyBuilderStoreContext,
} from '../../store/strategy-builder';
import type { StrategyTree } from '../../types/strategy-builder';

interface StrategyBuilderStoreProviderProps {
  /** The strategy tree to initialize the store with */
  tree: StrategyTree;
  /** Children to render within the scoped store context */
  children: React.ReactNode;
}

/**
 * Provider component for scoped strategy builder stores.
 *
 * Creates an isolated store instance with the provided tree, allowing
 * multiple independent strategy visualizations on the same page.
 *
 * @example
 * ```tsx
 * <StrategyBuilderStoreProvider tree={parsedTree}>
 *   <TreeNode blockId={parsedTree.rootId} readOnly />
 * </StrategyBuilderStoreProvider>
 * ```
 */
export function StrategyBuilderStoreProvider({
  tree,
  children,
}: StrategyBuilderStoreProviderProps) {
  // Create a new store instance with the provided tree
  // Memoize to avoid recreating on every render
  const store = useMemo(() => createStrategyBuilderStore(tree), [tree]);

  return (
    <StrategyBuilderStoreContext.Provider value={store}>
      {children}
    </StrategyBuilderStoreContext.Provider>
  );
}
