import { useEffect, useMemo, useRef, useState } from 'react';

import { ShapeLayer } from '../../marketing/components/ShapeLayer';
import { chartArt, SECTION_SHAPES } from '../../marketing/lib/sectionArt';

/** The site's background chart, in the accent, filling the panel behind the example backtest. */
export function AuthArt() {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setSize({ width: el.clientWidth, height: el.clientHeight });
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const groups = useMemo(
    () =>
      chartArt(SECTION_SHAPES.top, {
        width: size.width,
        top: size.height * 0.14,
        height: Math.min(420, size.height * 0.5),
      }),
    [size.width, size.height]
  );

  return (
    <div ref={ref} className="auth-art" aria-hidden="true">
      {size.width > 0 && size.height > 0 && (
        <ShapeLayer width={size.width} height={size.height} groups={groups} inheritColor />
      )}
    </div>
  );
}
