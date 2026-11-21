import { describe, expect, it } from 'vitest';

import { readingText } from '../rules/evaluate';
import { phoneNote, stepFor } from '../rules/phoneEdit';

describe('phone value editing', () => {
  it('steps whole numbers by one and fractions by a tenth', () => {
    expect(stepFor(70)).toBe(1);
    expect(stepFor(0.5)).toBe(0.1);
  });

  it('writes the version note from the change', () => {
    expect(phoneNote(1, 70, 72)).toBe('Rule 1 line from 70 to 72');
    expect(phoneNote(2, 0.5, 0.6)).toBe('Rule 2 line from 0.5 to 0.6');
  });

  it('formats readings', () => {
    expect(readingText(73.84)).toBe('73.8');
    expect(readingText(70)).toBe('70');
    expect(readingText(12345.6)).toBe('12,346');
  });
});
