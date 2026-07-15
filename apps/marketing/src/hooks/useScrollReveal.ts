import { useEffect } from 'react';

/**
 * Scroll-reveal — a faithful React port of the original static page's
 * IntersectionObserver reveal, kept deliberately "bulletproof": content must
 * never stay hidden.
 *
 * - Honors `prefers-reduced-motion` and missing IntersectionObserver by
 *   revealing everything immediately.
 * - Otherwise observes every `.reveal` element, plus an independent scroll/resize
 *   fail-safe that reveals anything at/near the viewport, plus a final 1.4s
 *   timeout that reveals all — so a flaky observer can never blank the page.
 *
 * Runs once against the whole document (matching the original global querySelectorAll),
 * so `.reveal` may be composed onto any element without a wrapper that would
 * disturb the surrounding grid/flow layout.
 */
export function useScrollReveal(): void {
  useEffect(() => {
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    const revs = Array.from(document.querySelectorAll<HTMLElement>('.reveal'));
    const revealAll = (): void => revs.forEach((el) => el.classList.add('in'));

    if (reduce || !('IntersectionObserver' in window)) {
      revealAll();
      return;
    }

    let io: IntersectionObserver | null = null;
    try {
      io = new IntersectionObserver(
        (entries) => {
          entries.forEach((e) => {
            if (e.isIntersecting) {
              e.target.classList.add('in');
              io?.unobserve(e.target);
            }
          });
        },
        { threshold: 0, rootMargin: '0px 0px 60px 0px' }
      );
      revs.forEach((el) => io?.observe(el));
    } catch {
      revealAll();
      return;
    }

    // Independent fail-safe: reveal anything at/near the viewport regardless of observer.
    const revealInView = (): void => {
      const limit = window.innerHeight * 1.2;
      revs.forEach((el) => {
        if (el.getBoundingClientRect().top < limit) el.classList.add('in');
      });
    };
    revealInView();
    window.addEventListener('scroll', revealInView, { passive: true });
    window.addEventListener('resize', revealInView);

    // Final guarantee: nothing can remain blank.
    const timer = window.setTimeout(revealAll, 1400);

    return () => {
      io?.disconnect();
      window.removeEventListener('scroll', revealInView);
      window.removeEventListener('resize', revealInView);
      window.clearTimeout(timer);
    };
  }, []);
}
