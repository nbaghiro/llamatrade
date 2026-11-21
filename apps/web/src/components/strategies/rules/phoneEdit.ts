import { readingText } from './evaluate';

/** The step a stepper moves a threshold by: whole numbers move by one, others by a tenth. */
export function stepFor(value: number): number {
  return Number.isInteger(value) ? 1 : 0.1;
}

/** "Rule 1 line from 70 to 72", the note a phone edit saves with. */
export function phoneNote(rule: number, was: number, now: number): string {
  return `Rule ${rule} line from ${readingText(was)} to ${readingText(now)}`;
}
