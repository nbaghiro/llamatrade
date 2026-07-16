/**
 * Pure SVG path math — identical in spirit to the web app's hand-authored
 * charts, so the geometry is shared across web and native (only the host tag
 * differs: <path> vs react-native-svg <Path>).
 */

/** Polyline through normalized values, fit to a WxH box. */
export function linePath(values: number[], w: number, h: number, pad = 3): string {
  if (values.length < 2) return '';
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = (w - pad * 2) / (values.length - 1);
  return values
    .map((v, i) => {
      const x = pad + i * stepX;
      const y = pad + (h - pad * 2) * (1 - (v - min) / span);
      return `${i === 0 ? 'M' : 'L'}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(' ');
}

/** Closed area under the polyline (for the fill). */
export function areaPath(values: number[], w: number, h: number, pad = 3): string {
  const line = linePath(values, w, h, pad);
  if (!line) return '';
  return `${line} L${(w - pad).toFixed(1)},${h} L${pad.toFixed(1)},${h} Z`;
}
