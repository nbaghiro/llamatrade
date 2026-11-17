import { useMemo } from 'react';

import { chartArt, SECTION_SHAPES, type SectionArtId } from '../lib/sectionArt';

import { ShapeLayer } from './ShapeLayer';

/**
 * A section's background chart behind the top of a phone screen, fading out before the content.
 * `full` covers the whole screen, for the lock screen.
 */
export function PhoneArt({
  shape,
  width,
  height,
  top,
  band,
  full = false,
}: {
  shape: SectionArtId;
  width: number;
  height: number;
  /** Top of the price band, in px. */
  top: number;
  /** Height of the price band, in px. */
  band: number;
  full?: boolean;
}) {
  const groups = useMemo(
    () => chartArt(SECTION_SHAPES[shape], { width, top, height: band }),
    [shape, width, top, band]
  );
  return (
    <div className={full ? 'phone-art full' : 'phone-art'} style={{ height }} aria-hidden="true">
      <ShapeLayer width={width} height={height} groups={groups} inheritColor />
    </div>
  );
}
