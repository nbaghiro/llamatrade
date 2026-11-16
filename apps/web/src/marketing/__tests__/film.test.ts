import { describe, expect, it } from 'vitest';

import { filmOpening, filmScrollFor, filmSize, filmStep } from '../lib/film';

describe('filmSize', () => {
  it('shows three frames on wide screens, capped at 1200px of frames and gaps', () => {
    const s = filmSize(1440);
    expect(s.count).toBe(3);
    expect(s.gap).toBe(32);
    expect(s.frame).toBe(Math.floor((1200 - 64) / 3));
    expect(s.view).toBe(3 * s.frame + 64);
    expect(s.pad).toBe(56);
  });

  it('switches to one frame below 1000px', () => {
    expect(filmSize(999).count).toBe(1);
    expect(filmSize(1000).count).toBe(3);
  });

  it('keeps the visible frame count odd so one frame is centred', () => {
    for (const w of [320, 390, 768, 999, 1000, 1280, 1920]) expect(filmSize(w).count % 2).toBe(1);
  });

  it('fills a phone with one frame and no faded edge', () => {
    const s = filmSize(390);
    expect(s.frame).toBe(390);
    expect(s.view).toBe(390);
    expect(s.pad).toBe(0);
    expect(s.trackPad).toBe(0);
  });

  it('pads the track so the first and last frames can sit centred', () => {
    const s = filmSize(1440);
    expect(s.trackPad).toBe((s.view - s.frame) / 2 + s.pad);
  });

  it('never returns a zero or negative frame', () => {
    expect(filmSize(0).frame).toBeGreaterThan(0);
    expect(filmSize(-20).frame).toBeGreaterThan(0);
  });
});

describe('film scrolling', () => {
  it('opens on the middle frame', () => {
    expect(filmOpening(9)).toBe(4);
    expect(filmOpening(1)).toBe(0);
    expect(filmOpening(0)).toBe(0);
  });

  it('centres frame i at i steps from the start', () => {
    const s = filmSize(1440);
    expect(filmStep(s)).toBe(s.frame + s.gap);
    expect(filmScrollFor(s, 4)).toBe(4 * (s.frame + s.gap));
    expect(filmScrollFor(s, -1)).toBe(0);
  });
});
