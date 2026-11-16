import { useLayoutEffect, useMemo, useState, type RefObject } from 'react';

import { chartArt, SECTION_SHAPES } from '../lib/sectionArt';

import { ShapeLayer } from './ShapeLayer';

/** A full-width candle chart behind the hero, sized to end just above the facts row. */
export function HeroArt({
  section,
  facts,
}: {
  section: RefObject<HTMLElement>;
  facts: RefObject<HTMLElement>;
}) {
  const [size, setSize] = useState({ width: 0, height: 0 });

  useLayoutEffect(() => {
    const sec = section.current;
    if (!sec) return;
    const measure = () => {
      const f = facts.current;
      const top = sec.getBoundingClientRect().top;
      const height = Math.round(f ? f.getBoundingClientRect().top - top - 24 : sec.offsetHeight);
      setSize((s) =>
        s.width === sec.clientWidth && s.height === height ? s : { width: sec.clientWidth, height }
      );
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(measure);
    ro.observe(sec);
    return () => ro.disconnect();
  }, [section, facts]);

  const groups = useMemo(
    () =>
      chartArt(SECTION_SHAPES.top, {
        width: size.width,
        top: 70,
        height: Math.min(360, size.height * 0.55),
      }),
    [size.width, size.height]
  );

  return (
    <div className="hero-art" style={{ height: size.height || undefined }} aria-hidden="true">
      {size.width > 0 && size.height > 0 && (
        <ShapeLayer width={size.width} height={size.height} groups={groups} inheritColor />
      )}
    </div>
  );
}
