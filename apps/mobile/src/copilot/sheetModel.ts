/** Where the Copilot half sheet rests (copilot/phone B): half height, full height, or closed. */
export type SheetStop = 'half' | 'full' | 'closed';

export interface SheetGeometry {
  /** Sheet top offset at full height, from the top of the window. */
  fullTop: number;
  /** Sheet top offset at half height. */
  halfTop: number;
  windowHeight: number;
}

export function sheetGeometry(windowHeight: number, topInset: number): SheetGeometry {
  return {
    fullTop: topInset + 8,
    halfTop: Math.round(windowHeight * 0.42),
    windowHeight,
  };
}

/** The top offset for a stop. */
export function stopTop(stop: SheetStop, g: SheetGeometry): number {
  return stop === 'full' ? g.fullTop : stop === 'half' ? g.halfTop : g.windowHeight;
}

const FLING = 0.6;

/**
 * Where a drag released at `top` with vertical velocity `vy` (points per ms, down positive)
 * settles: a fling picks the next stop in its direction, otherwise the nearest stop wins.
 */
export function settle(top: number, vy: number, g: SheetGeometry): SheetStop {
  if (vy > FLING) return top < g.halfTop - 20 ? 'half' : 'closed';
  if (vy < -FLING) return 'full';
  const stops: SheetStop[] = ['full', 'half', 'closed'];
  const closedCut = g.halfTop + (g.windowHeight - g.halfTop) * 0.35;
  if (top > closedCut) return 'closed';
  return stops
    .filter((s) => s !== 'closed')
    .reduce((best, s) => (Math.abs(stopTop(s, g) - top) < Math.abs(stopTop(best, g) - top) ? s : best));
}
