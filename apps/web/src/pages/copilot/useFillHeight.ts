import { useLayoutEffect, useRef, useState, type RefObject } from 'react';

/** Space the phone tab bar takes under the page. */
const PHONE_BAR = 84;
const PHONE_MAX = 767;

/**
 * The height that fills the window from the element's top edge down, less the phone tab bar.
 * Banners above it (offline, a frozen sleeve) move the top edge, so it is measured, not assumed.
 */
export function useFillHeight<T extends HTMLElement>(): [RefObject<T>, number | null] {
  const ref = useRef<T>(null);
  const [height, setHeight] = useState<number | null>(null);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => {
      const top = el.getBoundingClientRect().top + window.scrollY;
      const bar = window.innerWidth <= PHONE_MAX ? PHONE_BAR : 0;
      setHeight(Math.max(240, window.innerHeight - top - bar));
    };
    measure();
    window.addEventListener('resize', measure);
    const ro = typeof ResizeObserver === 'undefined' ? null : new ResizeObserver(measure);
    ro?.observe(document.body);
    return () => {
      window.removeEventListener('resize', measure);
      ro?.disconnect();
    };
  }, []);

  return [ref, height];
}
