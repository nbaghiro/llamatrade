import { describe, expect, it } from 'vitest';

import { trapTarget } from '../useModal';

const el = (name: string) => ({ name }) as unknown as HTMLElement;
const [a, b, c] = [el('a'), el('b'), el('c')];
const items = [a, b, c];

describe('trapTarget', () => {
  it('wraps forward from the last item to the first', () => {
    expect(trapTarget(items, c, false)).toBe(a);
  });

  it('wraps backward from the first item to the last', () => {
    expect(trapTarget(items, a, true)).toBe(c);
  });

  it('lets Tab move normally between inner items', () => {
    expect(trapTarget(items, a, false)).toBeNull();
    expect(trapTarget(items, c, true)).toBeNull();
  });

  it('pulls focus back in when it sits outside the panel', () => {
    expect(trapTarget(items, el('outside'), false)).toBe(a);
    expect(trapTarget(items, null, true)).toBe(c);
  });

  it('does nothing when the panel has no focusable items', () => {
    expect(trapTarget([], a, false)).toBeNull();
  });
});
