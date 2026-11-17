/** Film strip geometry: fixed-width frames, a viewport an odd number of frames wide. */

export interface FilmSize {
  /** Frames visible at once: 3 on wide screens, 1 otherwise. */
  count: number;
  gap: number;
  frame: number;
  /** Width of the visible frames and the gaps between them. */
  view: number;
  /** Faded edge on each side of the view. */
  pad: number;
  /** Inline padding on the track: the faded edge, so the first and last frames sit at the view's edges. */
  trackPad: number;
}

export const FILM_WIDE = 1000;
export const FILM_MAX = 1200;

export function filmSize(width: number): FilmSize {
  const w = Math.max(0, width);
  const wide = w >= FILM_WIDE;
  const count = wide ? 3 : 1;
  const gap = wide ? 32 : 16;
  const frame = Math.max(1, Math.floor((Math.min(w, FILM_MAX) - gap * (count - 1)) / count));
  const view = count * frame + (count - 1) * gap;
  const pad = Math.min(56, Math.max(0, (w - view) / 2));
  return { count, gap, frame, view, pad, trackPad: pad };
}

/** Distance between neighbouring frames, one arrow press. */
export function filmStep(size: FilmSize): number {
  return size.frame + size.gap;
}

/** scrollLeft that centres frame `index` in the view, clamped to the ends of the strip. */
export function filmScrollFor(size: FilmSize, index: number, frames: number): number {
  const side = (size.count - 1) / 2;
  const last = Math.max(0, frames - size.count);
  return Math.min(last, Math.max(0, index - side)) * filmStep(size);
}

/** The frame the strip opens on: the middle one. */
export function filmOpening(frames: number): number {
  return Math.max(0, Math.floor(frames / 2));
}
