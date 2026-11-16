import { useLayoutEffect, useMemo, useRef, useState } from 'react';

import { chartArt, SECTION_SHAPES, sectionBox, type SectionArtId } from '../lib/sectionArt';

import { ShapeLayer } from './ShapeLayer';

interface Size {
  width: number;
  sectionHeight: number;
  headX: number;
  headY: number;
}

/** A full-width chart behind its parent section, clear behind the heading, drawn in on first view. */
export function SectionArt({ id }: { id: SectionArtId }) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<Size | null>(null);
  const [on, setOn] = useState(false);

  useLayoutEffect(() => {
    const el = ref.current;
    const sec = el?.parentElement;
    if (!el || !sec) return;
    const measure = () => {
      const width = document.documentElement.clientWidth;
      const top = sec.getBoundingClientRect().top;
      const h2 = sec.querySelector('h2');
      const head = sec.querySelector('.sec-h, .split > div') ?? h2;
      const hr = h2?.getBoundingClientRect();
      const box = head?.getBoundingClientRect();
      const next: Size = {
        width,
        sectionHeight: sec.offsetHeight,
        headY: hr ? Math.round(hr.top - top + hr.height / 2 + 20) : 190,
        headX: box ? Math.round(((box.left + box.width / 2) / width) * 100) : 50,
      };
      setSize((s) =>
        s &&
        s.width === next.width &&
        s.sectionHeight === next.sectionHeight &&
        s.headY === next.headY &&
        s.headX === next.headX
          ? s
          : next
      );
    };
    measure();
    document.fonts?.ready.then(measure, measure);
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(measure);
    ro.observe(sec);
    return () => ro.disconnect();
  }, []);

  useLayoutEffect(() => {
    const el = ref.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setOn(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setOn(true);
          io.disconnect();
        }
      },
      { rootMargin: '0px 0px -15% 0px' }
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  const layout = useMemo(
    () => (size ? sectionBox(size.width, size.sectionHeight, size.headY) : null),
    [size]
  );
  const groups = useMemo(
    () => (layout ? chartArt(SECTION_SHAPES[id], layout.box) : []),
    [id, layout]
  );

  return (
    <div
      ref={ref}
      className={on ? 'sec-art on' : 'sec-art'}
      style={
        size && layout
          ? {
              height: layout.height,
              ['--sa-cx' as string]: `${size.headX}%`,
              ['--sa-cy' as string]: `${size.headY}px`,
            }
          : undefined
      }
      aria-hidden="true"
    >
      {size && layout && groups.length > 0 && (
        <ShapeLayer width={size.width} height={layout.height} groups={groups} inheritColor />
      )}
    </div>
  );
}
