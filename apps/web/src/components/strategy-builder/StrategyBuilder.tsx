import { useCallback, useEffect } from 'react';

import { useStrategyBuilderStoreWithContext } from '../../store/strategy-builder';

import { Canvas } from './Canvas';
import { CodeEditor } from './CodeEditor';
import { BuilderInsightsBar } from './panels/BuilderInsightsBar';
import { BuilderTopBar } from './panels/BuilderTopBar';

interface StrategyBuilderProps {
  readOnly?: boolean;
}

export function StrategyBuilder({ readOnly }: StrategyBuilderProps) {
  const { ui, viewMode, compactView, deleteBlock, undo, redo, canUndo, canRedo, getBlock } =
    useStrategyBuilderStoreWithContext();

  const isViewOnly = readOnly || compactView;

  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (readOnly) return;
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;

      if ((e.metaKey || e.ctrlKey) && e.key === 'z' && !e.shiftKey) {
        e.preventDefault();
        if (canUndo()) undo();
        return;
      }
      if (((e.metaKey || e.ctrlKey) && e.shiftKey && e.key === 'z') || ((e.metaKey || e.ctrlKey) && e.key === 'y')) {
        e.preventDefault();
        if (canRedo()) redo();
        return;
      }
      if (e.key === 'Backspace' || e.key === 'Delete') {
        e.preventDefault();
        if (ui.selectedBlockId) {
          const block = getBlock(ui.selectedBlockId);
          if (block && block.type !== 'root') deleteBlock(ui.selectedBlockId);
        }
      }
    },
    [ui.selectedBlockId, canUndo, canRedo, undo, redo, deleteBlock, getBlock, readOnly]
  );

  useEffect(() => {
    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [handleKeyDown]);

  return (
    <div className={`flex flex-col overflow-hidden bg-bone ${readOnly ? 'h-full' : 'h-[calc(100vh-56px)]'}`}>
      <BuilderTopBar readOnly={readOnly} />

      <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
        {viewMode === 'split' ? (
          <div className="grid min-h-0 flex-1 grid-cols-1 lg:grid-cols-2">
            <div className="flex min-h-0 flex-col overflow-hidden border-b-2 border-ink bg-grid px-4 pt-3 lg:border-b-0 lg:border-r-2">
              <Canvas readOnly={readOnly} />
            </div>
            <div className="flex min-h-0 flex-col overflow-hidden">
              <CodeEditor readOnly={isViewOnly} />
            </div>
          </div>
        ) : viewMode === 'code' ? (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
            <CodeEditor readOnly={isViewOnly} />
          </div>
        ) : (
          <div className="flex min-h-0 flex-1 flex-col overflow-hidden bg-grid px-4 pt-3">
            <Canvas readOnly={readOnly} />
          </div>
        )}
      </div>

      {!readOnly && <BuilderInsightsBar />}
    </div>
  );
}
