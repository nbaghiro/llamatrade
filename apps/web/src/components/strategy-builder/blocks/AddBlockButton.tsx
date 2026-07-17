import { PlusCircle } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import type { BlockId } from '@llamatrade/core/strategy/types';
import { BlockPicker } from '../panels/BlockPicker';

interface AddBlockButtonProps {
  parentId: BlockId;
}

export function AddBlockButton({ parentId }: AddBlockButtonProps) {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

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
          w-full flex items-center gap-3 px-4 py-3 border-2 border-dashed
          transition-colors overflow-hidden
          ${
            isOpen
              ? 'border-orange-500 bg-orange-50 text-orange-700'
              : 'border-ink/40 text-ink/60 hover:border-ink hover:text-ink hover:bg-bone'
          }
        `}
      >
        <PlusCircle className="w-5 h-5 shrink-0" />
        <span className="font-mono font-bold uppercase tracking-wide whitespace-nowrap">Add a Block</span>
        <span className="text-sm opacity-75 truncate">Stocks or Securities, Weights, Conditions...</span>
      </button>

      {isOpen && <BlockPicker parentId={parentId} onClose={() => setIsOpen(false)} />}
    </div>
  );
}
