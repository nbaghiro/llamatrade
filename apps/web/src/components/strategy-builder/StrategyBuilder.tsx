import { useCallback, useEffect } from 'react';

import { useStrategyBuilderStore } from '../../store/strategy-builder';

import { RootBlock } from './blocks/RootBlock';
import { Canvas } from './Canvas';
import { CodeEditor } from './CodeEditor';
import { LeftPanel } from './panels/LeftPanel';
import { RightPanel } from './panels/RightPanel';

export function StrategyBuilder() {
  const { tree, ui, viewMode, deleteBlock, undo, redo, canUndo, canRedo, getBlock } = useStrategyBuilderStore();
  const rootBlock = tree.blocks[tree.rootId];

  // Keyboard shortcuts
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      // Ignore if typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) {
        return;
      }

      // Undo: Cmd/Ctrl + Z
      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        if (canUndo()) {
          undo();
        }
        return;
      }

      // Redo: Cmd/Ctrl + Shift + Z or Cmd/Ctrl + Y
      if (
        ((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'z') ||
        ((e.metaKey || e.ctrlKey) && e.key === 'y')
      ) {
        e.preventDefault();
        if (canRedo()) {
          redo();
        }
        return;
      }

      // Delete: Backspace or Delete
      if (e.key === 'Backspace' || e.key === 'Delete') {
        e.preventDefault();
        if (ui.selectedBlockId) {
          const block = getBlock(ui.selectedBlockId);
          // Don't delete root
          if (block && block.type !== 'root') {
            deleteBlock(ui.selectedBlockId);
          }
        }
        return;
      }
    },
    [ui.selectedBlockId, canUndo, canRedo, undo, redo, deleteBlock, getBlock]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div className="flex h-[calc(100vh-56px)] overflow-hidden bg-gray-50 dark:bg-gray-950 bg-dotted-grid p-6 gap-6">
      {/* Left Panel - Strategy Details */}
      <LeftPanel />

      {/* Center - Canvas or Code Editor */}
      <div className="flex-1 min-w-0 flex flex-col overflow-hidden pt-4 px-6">
        {/* Root Block - always visible */}
        {rootBlock && rootBlock.type === 'root' && (
          <div className="flex-shrink-0 mb-4">
            <RootBlock block={rootBlock} />
          </div>
        )}

        {/* Main content area - tree or code editor */}
        {viewMode === 'tree' ? (
          <Canvas />
        ) : (
          <div className="flex-1 min-h-0 overflow-hidden">
            <CodeEditor />
          </div>
        )}
      </div>

      {/* Right Panel - Preview */}
      <RightPanel />
    </div>
  );
}
