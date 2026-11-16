import { describe, expect, it } from 'vitest';

import { radioKeyTarget } from '../radioKeys';

describe('radioKeyTarget', () => {
  it('moves forward and back with the arrow keys', () => {
    expect(radioKeyTarget('ArrowRight', 3, 12)).toBe(4);
    expect(radioKeyTarget('ArrowDown', 3, 12)).toBe(4);
    expect(radioKeyTarget('ArrowLeft', 3, 12)).toBe(2);
    expect(radioKeyTarget('ArrowUp', 3, 12)).toBe(2);
  });

  it('wraps at both ends', () => {
    expect(radioKeyTarget('ArrowRight', 11, 12)).toBe(0);
    expect(radioKeyTarget('ArrowLeft', 0, 12)).toBe(11);
  });

  it('jumps to the first and last with Home and End', () => {
    expect(radioKeyTarget('Home', 7, 12)).toBe(0);
    expect(radioKeyTarget('End', 2, 12)).toBe(11);
  });

  it('ignores other keys and empty groups', () => {
    expect(radioKeyTarget('Enter', 3, 12)).toBeNull();
    expect(radioKeyTarget('Tab', 3, 12)).toBeNull();
    expect(radioKeyTarget('ArrowRight', 0, 0)).toBeNull();
  });
});
