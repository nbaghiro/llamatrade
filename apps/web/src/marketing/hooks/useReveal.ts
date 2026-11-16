import { useEffect, type RefObject } from 'react';

import { REDUCED_MOTION } from './useMedia';

/**
 * Fades `.rise` elements in as they enter the viewport. Everything shows at once with reduced
 * motion or without IntersectionObserver, and after 2.2 s regardless, so nothing stays hidden.
 */
export function useReveal(root: RefObject<HTMLElement>): void {
  useEffect(() => {
    const host = root.current;
    if (!host) return;
    const els = Array.from(host.querySelectorAll<HTMLElement>('.rise'));
    const showAll = () => els.forEach((e) => e.classList.add('in'));
    const reduce = window.matchMedia?.(REDUCED_MOTION).matches ?? false;
    if (reduce || typeof IntersectionObserver === 'undefined') {
      showAll();
      return;
    }
    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) {
            e.target.classList.add('in');
            io.unobserve(e.target);
          }
        }),
      { rootMargin: '0px 0px -6% 0px' }
    );
    els.forEach((e) => io.observe(e));
    const timer = window.setTimeout(showAll, 2200);
    return () => {
      io.disconnect();
      window.clearTimeout(timer);
    };
  }, [root]);
}

/** Calls `onEnter` once, the first time the element is `threshold` visible. */
export function useOnEnter(
  target: RefObject<HTMLElement>,
  onEnter: () => void,
  threshold = 0.3
): void {
  useEffect(() => {
    const el = target.current;
    if (!el) return;
    if (typeof IntersectionObserver === 'undefined') {
      onEnter();
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          onEnter();
          io.disconnect();
        }
      },
      { threshold }
    );
    io.observe(el);
    return () => io.disconnect();
  }, [target, onEnter, threshold]);
}
