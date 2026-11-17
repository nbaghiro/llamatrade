import { useEffect } from 'react';

/** Sets the browser tab to "Title · LlamaTrade". */
export function useDocumentTitle(title: string | undefined) {
  useEffect(() => {
    if (!title) return;
    const before = document.title;
    document.title = `${title} · LlamaTrade`;
    return () => {
      document.title = before;
    };
  }, [title]);
}
