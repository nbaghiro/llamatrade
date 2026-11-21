import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { describe, expect, it, vi } from 'vitest';

import { ACCENTS, DARK_ACCENTS, LIGHT_ACCENTS } from '../../theme/accents';
import {
  applyTheme,
  DEFAULT_THEME,
  migrateTheme,
  resolveTheme,
  sanitizeTheme,
  THEME_STORAGE_KEY,
  watchScheme,
  type ResolvedTheme,
  type SchemeQuery,
  type ThemePrefs,
} from '../theme';

const readText = (rel: string) =>
  readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');

describe('sanitizeTheme', () => {
  it('returns defaults for anything that is not an object', () => {
    expect(sanitizeTheme(null)).toEqual(DEFAULT_THEME);
    expect(sanitizeTheme('dark')).toEqual(DEFAULT_THEME);
    expect(sanitizeTheme(undefined)).toEqual(DEFAULT_THEME);
  });

  it('defaults to system mode, Graphite and White surfaces, and the neutral Ink accent', () => {
    expect(DEFAULT_THEME).toEqual({
      mode: 'system',
      darkSurface: 'slate',
      lightSurface: 'white',
      darkAccent: 'neutral',
      lightAccent: 'neutral',
    });
  });

  it('keeps valid fields and replaces invalid ones individually', () => {
    expect(
      sanitizeTheme({
        mode: 'light',
        darkSurface: 'purple',
        lightSurface: 'warm',
        darkAccent: 'pink',
        lightAccent: 'neon',
      })
    ).toEqual({
      mode: 'light',
      darkSurface: 'slate',
      lightSurface: 'warm',
      darkAccent: 'pink',
      lightAccent: 'neutral',
    });
  });

  it('migrates version 1 default accents to Ink and keeps chosen ones', () => {
    expect(migrateTheme({ darkAccent: 'slate', lightAccent: 'ocean' }, 1)).toMatchObject({
      darkAccent: 'neutral',
      lightAccent: 'neutral',
    });
    expect(migrateTheme({ darkAccent: 'pink', lightAccent: 'rust' }, 1)).toMatchObject({
      darkAccent: 'pink',
      lightAccent: 'rust',
    });
    expect(migrateTheme({ darkAccent: 'slate', lightAccent: 'ocean' }, 2)).toMatchObject({
      darkAccent: 'slate',
      lightAccent: 'ocean',
    });
  });

  it('rejects an accent that belongs to the other mode', () => {
    const prefs = sanitizeTheme({ darkAccent: 'navy', lightAccent: 'cyan' });
    expect(prefs.darkAccent).toBe('neutral');
    expect(prefs.lightAccent).toBe('neutral');
  });

  it('rejects the dropped dark Amber accent', () => {
    expect(sanitizeTheme({ darkAccent: 'amber' }).darkAccent).toBe('neutral');
  });

  it('ignores the retired Monolith shape', () => {
    expect(sanitizeTheme({ theme: 'light' })).toEqual(DEFAULT_THEME);
  });
});

describe('resolveTheme', () => {
  const prefs: ThemePrefs = {
    mode: 'system',
    darkSurface: 'slate',
    lightSurface: 'white',
    darkAccent: 'violet',
    lightAccent: 'pine',
  };

  it('follows the OS scheme in system mode', () => {
    expect(resolveTheme(prefs, false)).toEqual({
      mode: 'dark',
      theme: 'slate',
      light: 'white',
      acc: 'violet',
    });
    expect(resolveTheme(prefs, true)).toEqual({
      mode: 'light',
      theme: 'slate',
      light: 'white',
      acc: 'pine',
    });
  });

  it('ignores the OS scheme when a mode is chosen', () => {
    expect(resolveTheme({ ...prefs, mode: 'dark' }, true).mode).toBe('dark');
    expect(resolveTheme({ ...prefs, mode: 'light' }, false).mode).toBe('light');
  });

  it('uses the accent of the resolved mode', () => {
    expect(resolveTheme({ ...prefs, mode: 'dark' }, true).acc).toBe('violet');
    expect(resolveTheme({ ...prefs, mode: 'light' }, false).acc).toBe('pine');
  });
});

describe('applyTheme', () => {
  it('writes all four attributes', () => {
    const root = { dataset: {} as Record<string, string | undefined> };
    applyTheme({ mode: 'light', theme: 'black', light: 'warm', acc: 'rust' }, root);
    expect(root.dataset).toEqual({ mode: 'light', theme: 'black', light: 'warm', acc: 'rust' });
  });
});

describe('watchScheme', () => {
  function fakeQuery(initial: boolean) {
    const listeners = new Set<() => void>();
    const query: SchemeQuery & { flip: (v: boolean) => void; count: () => number } = {
      matches: initial,
      addEventListener: (_t, l) => listeners.add(l),
      removeEventListener: (_t, l) => listeners.delete(l),
      flip(v) {
        this.matches = v;
        listeners.forEach((l) => l());
      },
      count: () => listeners.size,
    };
    return query;
  }

  it('reports each switch and stops after unsubscribe', () => {
    const query = fakeQuery(false);
    const seen: boolean[] = [];
    const stop = watchScheme(query, (light) => seen.push(light));
    query.flip(true);
    query.flip(false);
    stop();
    query.flip(true);
    expect(seen).toEqual([true, false]);
    expect(query.count()).toBe(0);
  });

  it('re-resolves a system preference on each switch', () => {
    const query = fakeQuery(false);
    const modes: string[] = [];
    watchScheme(query, (light) => modes.push(resolveTheme(DEFAULT_THEME, light).mode));
    query.flip(true);
    query.flip(false);
    expect(modes).toEqual(['light', 'dark']);
  });
});

describe('public/theme-init.js', () => {
  const source = readText('../../../public/theme-init.js');

  function runInit(stored: unknown, prefersLight: boolean, modeDefault?: string): ResolvedTheme {
    const attrs: Record<string, string> = {};
    const documentElement = {
      setAttribute: (k: string, v: string) => {
        attrs[k] = v;
      },
      getAttribute: (k: string) => (k === 'data-mode-default' ? (modeDefault ?? null) : null),
    };
    const storage = {
      getItem: vi.fn((key: string) =>
        key === THEME_STORAGE_KEY && stored !== undefined ? JSON.stringify(stored) : null
      ),
    };
    const matchMedia = () => ({ matches: prefersLight });
    new Function('document', 'localStorage', 'matchMedia', source)(
      { documentElement },
      storage,
      matchMedia
    );
    return {
      mode: attrs['data-mode'] as ResolvedTheme['mode'],
      theme: attrs['data-theme'] as ResolvedTheme['theme'],
      light: attrs['data-light'] as ResolvedTheme['light'],
      acc: attrs['data-acc'],
    };
  }

  it('stays under 1 KB', () => {
    expect(new TextEncoder().encode(source).length).toBeLessThan(1024);
  });

  it.each([
    [undefined, false],
    [undefined, true],
    [{ state: { mode: 'light', lightAccent: 'rust', lightSurface: 'white' } }, false],
    [{ state: { mode: 'dark', darkAccent: 'lime', darkSurface: 'slate' } }, true],
    [{ state: { mode: 'system', darkAccent: 'pink', lightAccent: 'plum' } }, true],
    [{ state: { mode: 'system', darkAccent: 'pink', lightAccent: 'plum' } }, false],
    [{ state: { mode: 'dark', darkAccent: 'navy' } }, false],
    [{ state: { mode: 'light', lightAccent: 'cyan' } }, false],
    [{ state: { mode: 'purple', darkAccent: 'amber', darkSurface: 7 } }, false],
  ])('matches the store for %j (prefers light: %s)', (stored, prefersLight) => {
    const state = (stored as { state?: unknown } | undefined)?.state;
    expect(runInit(stored, prefersLight)).toEqual(resolveTheme(sanitizeTheme(state), prefersLight));
  });

  it('survives unreadable storage', () => {
    const attrs: Record<string, string> = {};
    new Function('document', 'localStorage', 'matchMedia', source)(
      {
        documentElement: {
          setAttribute: (k: string, v: string) => (attrs[k] = v),
          getAttribute: () => null,
        },
      },
      { getItem: () => '{not json' },
      () => ({ matches: false })
    );
    expect(attrs).toEqual({
      'data-mode': 'dark',
      'data-theme': 'slate',
      'data-light': 'white',
      'data-acc': 'neutral',
    });
  });

  it('moves a version 1 default accent to Ink, as the store migration does', () => {
    const v1 = { version: 1, state: { mode: 'dark', darkAccent: 'slate', lightAccent: 'ocean' } };
    expect(runInit(v1, false).acc).toBe('neutral');
    expect(runInit(v1, true).acc).toBe('neutral');
    expect(runInit({ version: 2, state: { mode: 'dark', darkAccent: 'slate' } }, false).acc).toBe(
      'slate'
    );
    expect(runInit({ version: 1, state: { mode: 'dark', darkAccent: 'pink' } }, false).acc).toBe(
      'pink'
    );
  });

  it('uses the page default mode when nothing is stored', () => {
    expect(runInit(undefined, true, 'dark').mode).toBe('dark');
    expect(runInit({ state: { mode: 'system' } }, true, 'dark').mode).toBe('light');
  });

  it('lists exactly the accents in accents.ts', () => {
    const lists = [...source.matchAll(/'([a-z ]+)'\.split\(' '\)/g)].map((m) => m[1].split(' '));
    expect(lists).toEqual([DARK_ACCENTS.map((a) => a.key), LIGHT_ACCENTS.map((a) => a.key)]);
  });
});

describe('tokens.css', () => {
  const css = readText('../../styles/tokens.css');

  it('defines a block for every accent in its mode', () => {
    for (const a of ACCENTS) {
      const selector =
        a.mode === 'dark'
          ? `:root:not([data-mode='light'])[data-acc='${a.key}']`
          : `:root[data-mode='light'][data-acc='${a.key}']`;
      expect(css, `${a.mode} ${a.key}`).toContain(selector);
    }
  });

  it('has 13 accents per mode and no Amber', () => {
    expect(DARK_ACCENTS).toHaveLength(13);
    expect(LIGHT_ACCENTS).toHaveLength(13);
    expect(css).not.toContain("data-acc='amber'");
  });
});
