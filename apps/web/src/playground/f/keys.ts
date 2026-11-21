import { useEffect, useState } from 'react';

/** j/k (or arrows) move a row selection, enter opens, e edits, space toggles. Ignored while typing. */
export function useListNav(
  count: number,
  handlers: {
    open?: (i: number) => void;
    edit?: (i: number) => void;
    toggle?: (i: number) => void;
  },
  initial = 0
) {
  const [sel, setSel] = useState(initial);
  const { open, edit, toggle } = handlers;
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const t = e.target;
      if (t instanceof HTMLInputElement || t instanceof HTMLTextAreaElement) return;
      if (document.documentElement.hasAttribute('data-fbar')) return;
      if (e.metaKey || e.ctrlKey || e.altKey) return;
      if (e.key === 'j' || e.key === 'ArrowDown') {
        e.preventDefault();
        setSel((s) => Math.min(count - 1, s + 1));
      } else if (e.key === 'k' || e.key === 'ArrowUp') {
        e.preventDefault();
        setSel((s) => Math.max(0, s - 1));
      } else if (e.key === 'Enter' && open) {
        e.preventDefault();
        open(sel);
      } else if (e.key === 'e' && edit) {
        e.preventDefault();
        edit(sel);
      } else if (e.key === ' ' && toggle) {
        e.preventDefault();
        toggle(sel);
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [count, sel, open, edit, toggle]);
  return [Math.min(sel, Math.max(0, count - 1)), setSel] as const;
}
