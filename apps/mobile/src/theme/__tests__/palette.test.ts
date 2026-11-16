import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  DARK_ACCENTS,
  DEFAULT_APPEARANCE,
  LIGHT_ACCENTS,
  accentsFor,
  colorsFor,
  isAccentFor,
  mixWithWhite,
  resolveMode,
  sanitizeAppearance,
  withAlpha,
} from '../palette.ts';

describe('resolveMode', () => {
  it('follows the device in system mode', () => {
    assert.equal(resolveMode('system', 'light'), 'light');
    assert.equal(resolveMode('system', 'dark'), 'dark');
  });

  it('falls back to dark when the device scheme is unknown', () => {
    assert.equal(resolveMode('system', null), 'dark');
    assert.equal(resolveMode('system', undefined), 'dark');
    assert.equal(resolveMode('system', 'unspecified'), 'dark');
  });

  it('ignores the device when a mode is chosen', () => {
    assert.equal(resolveMode('light', 'dark'), 'light');
    assert.equal(resolveMode('dark', 'light'), 'dark');
  });
});

describe('sanitizeAppearance', () => {
  it('returns the defaults for anything that is not an object', () => {
    for (const raw of [null, undefined, 'dark', 42, true]) {
      assert.deepEqual(sanitizeAppearance(raw), DEFAULT_APPEARANCE);
    }
  });

  it('keeps valid fields and replaces invalid ones field by field', () => {
    const prefs = sanitizeAppearance({
      mode: 'light',
      darkSurface: 'purple',
      lightSurface: 'warm',
      darkAccent: 'navy',
      lightAccent: 'rust',
    });
    assert.deepEqual(prefs, {
      mode: 'light',
      darkSurface: DEFAULT_APPEARANCE.darkSurface,
      lightSurface: 'warm',
      darkAccent: DEFAULT_APPEARANCE.darkAccent,
      lightAccent: 'rust',
    });
  });

  it('defaults to system mode, Slate and White surfaces, Slate blue and Ocean accents', () => {
    assert.deepEqual(DEFAULT_APPEARANCE, {
      mode: 'system',
      darkSurface: 'slate',
      lightSurface: 'white',
      darkAccent: 'slate',
      lightAccent: 'ocean',
    });
  });
});

describe('accents', () => {
  it('keeps dark and light accent lists separate', () => {
    assert.equal(accentsFor('dark'), DARK_ACCENTS);
    assert.equal(accentsFor('light'), LIGHT_ACCENTS);
    assert.ok(isAccentFor('dark', 'lime'));
    assert.ok(!isAccentFor('light', 'lime'));
    assert.ok(isAccentFor('light', 'navy'));
    assert.ok(!isAccentFor('dark', 'navy'));
    assert.ok(!isAccentFor('dark', 3));
  });

  it('has unique keys within each mode', () => {
    for (const list of [DARK_ACCENTS, LIGHT_ACCENTS]) {
      assert.equal(new Set(list.map((a) => a.key)).size, list.length);
    }
  });
});

describe('colorsFor', () => {
  it('matches tokens.css for dark Slate with the Slate blue accent', () => {
    const c = colorsFor({ ...DEFAULT_APPEARANCE, darkAccent: 'slate' }, 'dark');
    assert.equal(c.canvas, '#0f1316');
    assert.equal(c.panel, '#151a1f');
    assert.equal(c.accent, '#8fa4cf');
    assert.equal(c.accentFill, '#475f8a');
    assert.equal(c.accentInk, '#ffffff');
    assert.equal(c.accentSoft, 'rgba(143,164,207,0.16)');
    assert.equal(c.gain, '#3fbf7a');
    assert.equal(c.risk, '#f0a63a');
  });

  it('matches tokens.css for light White with the Slate blue accent', () => {
    const c = colorsFor({ ...DEFAULT_APPEARANCE, lightAccent: 'slate' }, 'light');
    assert.equal(c.canvas, '#fbfbfc');
    assert.equal(c.panel, '#ffffff');
    assert.equal(c.accent, '#475f8a');
    assert.equal(c.accentFill, '#475f8a');
    assert.equal(c.accentInk, '#ffffff');
    assert.equal(c.accentSoft, '#edeff3');
    assert.equal(c.loss, '#b3261e');
    assert.equal(c.risk, '#8a5a00');
  });

  it('uses the accent as the fill when an accent has no separate fill', () => {
    const c = colorsFor({ ...DEFAULT_APPEARANCE, darkAccent: 'lime' }, 'dark');
    assert.equal(c.accent, '#d9f05c');
    assert.equal(c.accentFill, '#d9f05c');
    assert.equal(c.accentInk, '#141a00');
  });

  it('applies the chosen surfaces', () => {
    assert.equal(
      colorsFor({ ...DEFAULT_APPEARANCE, darkSurface: 'slate' }, 'dark').canvas,
      '#0f1316'
    );
    assert.equal(
      colorsFor({ ...DEFAULT_APPEARANCE, lightSurface: 'warm' }, 'light').canvas,
      '#faf9f6'
    );
  });

  it('falls back to the default accent for an unknown key', () => {
    assert.equal(
      colorsFor({ ...DEFAULT_APPEARANCE, darkAccent: 'nope' }, 'dark').accent,
      '#8fa4cf'
    );
    assert.equal(
      colorsFor({ ...DEFAULT_APPEARANCE, lightAccent: 'nope' }, 'light').accent,
      '#1d4e89'
    );
  });
});

describe('colour helpers', () => {
  it('formats rgba from hex', () => {
    assert.equal(withAlpha('#ff9f43', 0.16), 'rgba(255,159,67,0.16)');
  });

  it('mixes toward white like color-mix', () => {
    assert.equal(mixWithWhite('#000000', 0.1), '#e6e6e6');
    assert.equal(mixWithWhite('#ffffff', 0.5), '#ffffff');
    assert.equal(mixWithWhite('#475f8a', 1), '#475f8a');
  });
});
