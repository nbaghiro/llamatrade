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
  /** Optional ID for view mode persistence (e.g., artifact ID) */
  previewId?: string;
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
 * <StrategyBuilderStoreProvider tree={parsedTree} previewId="artifact-123">
 *   <StrategyBuilder readOnly />
 * </StrategyBuilderStoreProvider>
 * ```
 */
export function StrategyBuilderStoreProvider({
  tree,
  previewId,
  children,
}: StrategyBuilderStoreProviderProps) {
  // Create a new store instance with the provided tree
  // Memoize to avoid recreating on every render
  const store = useMemo(
    () => createStrategyBuilderStore(tree, previewId),
    [tree, previewId]
  );

  return (
    <StrategyBuilderStoreContext.Provider value={store}>
      {children}
    </StrategyBuilderStoreContext.Provider>
  );
}
