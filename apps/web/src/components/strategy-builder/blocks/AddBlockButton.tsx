import { PlusCircle } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import type { BlockId } from '../../../types/strategy-builder';
import { BlockPicker } from '../panels/BlockPicker';

interface AddBlockButtonProps {
  parentId: BlockId;
}

export function AddBlockButton({ parentId }: AddBlockButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  // Close when clicking outside
  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [isOpen]);

  // Close on escape
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        setIsOpen(false);
      }
    };

    document.addEventListener('keydown', handleKeyDown);
    return () => document.removeEventListener('keydown', handleKeyDown);
  }, [isOpen]);

  return (
    <div ref={containerRef} className="relative">
      <button
        onClick={() => setIsOpen(!isOpen)}
        className={`
          w-full flex items-center gap-3 px-4 py-3 rounded-lg border-2 border-dashed
          transition-colors overflow-hidden
          ${
            isOpen
              ? 'border-primary-400 bg-primary-50 dark:bg-primary-900/20 text-primary-700 dark:text-primary-400'
              : 'border-gray-300 dark:border-gray-600 text-gray-500 dark:text-gray-400 hover:border-gray-400 dark:hover:border-gray-500 hover:text-gray-600 dark:hover:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800/50'
          }
        `}
      >
        <PlusCircle className="w-5 h-5 shrink-0" />
        <span className="font-medium whitespace-nowrap">Add a Block</span>
        <span className="text-sm opacity-75 truncate">Stocks or Securities, Weights, Conditions...</span>
      </button>

      {isOpen && <BlockPicker parentId={parentId} onClose={() => setIsOpen(false)} />}
    </div>
  );
}
