import { useEffect, useMemo, useRef, useState } from 'react';

import { ShapeLayer } from '../../marketing/components/ShapeLayer';
import { chartArt, SECTION_SHAPES, type SectionArtId } from '../../marketing/lib/sectionArt';

/**
 * The site's background chart in the accent, full width behind the top of a page. Place it as
 * the first child of a `.page` container; panels above it stay opaque.
 */
export function PageArt({ shape }: { shape: SectionArtId }) {
  const ref = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(0);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const measure = () => setWidth(el.clientWidth);
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const ro = new ResizeObserver(measure);
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const height = 460;
  const groups = useMemo(
    () => chartArt(SECTION_SHAPES[shape], { width, top: 40, height: 300 }),
    [shape, width]
  );

  return (
    <div ref={ref} className="page-art" aria-hidden="true">
      {width > 0 && <ShapeLayer width={width} height={height} groups={groups} inheritColor />}
    </div>
  );
}
