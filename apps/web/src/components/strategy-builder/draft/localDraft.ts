/**
 * An unsaved new strategy kept in this browser. The API creates a strategy only from code,
 * so a draft lives here until it's saved as version 1 (start2 A).
 */

const KEY = 'llamatrade-builder-draft';

export interface LocalDraft {
  dsl: string;
  name: string;
  savedAt: number;
}

function isDraft(v: unknown): v is LocalDraft {
  if (typeof v !== 'object' || v === null) return false;
  const r = v as Record<string, unknown>;
  return typeof r.dsl === 'string' && typeof r.name === 'string' && typeof r.savedAt === 'number';
}

export function readLocalDraft(): LocalDraft | null {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return null;
    const parsed: unknown = JSON.parse(raw);
    return isDraft(parsed) && parsed.dsl.trim() ? parsed : null;
  } catch {
    return null;
  }
}

export function writeLocalDraft(draft: Omit<LocalDraft, 'savedAt'>, now = Date.now()): void {
  try {
    localStorage.setItem(KEY, JSON.stringify({ ...draft, savedAt: now }));
  } catch {
    // Storage can be full or blocked; the draft still lives in memory.
  }
}

export function clearLocalDraft(): void {
  try {
    localStorage.removeItem(KEY);
  } catch {
    // Nothing to clear when storage is blocked.
  }
}
