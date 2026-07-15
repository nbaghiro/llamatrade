import { useEffect, useRef } from 'react';

/**
 * CursorAccent — the orange difference-blend cursor ring that trails the pointer
 * and swells ("hot") over interactive targets. Fine-pointer + motion only; a
 * faithful port of the original rAF follow loop. Hidden on touch/coarse pointers
 * and under reduced-motion (both via CSS and this guard).
 */
const HOT_SELECTOR = 'a, button, .btn, .bcard, .oc, .chip, .step, table.pos tbody tr';

export function CursorAccent() {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const cur = ref.current;
    if (!cur) return;

    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false;
    const fine = window.matchMedia?.('(hover:hover) and (pointer:fine)').matches ?? false;

    if (!fine || reduce) {
      cur.style.display = 'none';
      return;
    }

    let cx = window.innerWidth / 2;
    let cy = window.innerHeight / 2;
    let tx = cx;
    let ty = cy;
    let raf = 0;

    const onMove = (ev: MouseEvent): void => {
      tx = ev.clientX;
      ty = ev.clientY;
    };
    const loop = (): void => {
      cx += (tx - cx) * 0.28;
      cy += (ty - cy) * 0.28;
      cur.style.transform = `translate(${cx}px,${cy}px) translate(-50%,-50%)`;
      raf = requestAnimationFrame(loop);
    };
    const onOver = (ev: MouseEvent): void => {
      if ((ev.target as Element)?.closest(HOT_SELECTOR)) cur.classList.add('hot');
    };
    const onOut = (ev: MouseEvent): void => {
      if ((ev.target as Element)?.closest(HOT_SELECTOR)) cur.classList.remove('hot');
    };

    document.addEventListener('mousemove', onMove, { passive: true });
    document.addEventListener('mouseover', onOver);
    document.addEventListener('mouseout', onOut);
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseover', onOver);
      document.removeEventListener('mouseout', onOut);
    };
  }, []);

  return <div id="cursor" ref={ref} aria-hidden="true" />;
}
