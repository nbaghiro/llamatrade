import type { BlockId } from '@llamatrade/core/strategy/types';
import { Plus } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

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
        title="Add a block — stocks, weights, conditions…"
        className={`inline-flex items-center gap-1.5 border-2 border-dashed px-2.5 py-1.5 font-mono text-[12px] font-bold uppercase tracking-wide transition-colors ${
          isOpen
            ? 'border-orange-500 bg-orange-50 text-orange-700'
            : 'border-ink/30 text-ink/45 hover:border-ink hover:bg-bone hover:text-ink'
        }`}
      >
        <Plus className="h-3.5 w-3.5" /> Add block
      </button>

      {isOpen && <BlockPicker parentId={parentId} onClose={() => setIsOpen(false)} />}
    </div>
  );
}
