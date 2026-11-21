/** Template labels and grouping for the gallery (templates2 A); enum numbers as in strategy.proto. */

export const CATEGORY_LABELS: Record<number, string> = {
  1: 'Buy and hold',
  2: 'Tactical',
  3: 'Factor',
  4: 'Income',
  5: 'Trend',
  6: 'Mean reversion',
  7: 'Alternatives',
};

export const DIFFICULTY_LABELS: Record<number, string> = {
  1: 'Beginner',
  2: 'Intermediate',
  3: 'Advanced',
};

export interface TemplateLike {
  id: string;
  name: string;
  category: number;
  difficulty: number;
}

export interface CategoryGroup<T extends TemplateLike> {
  category: number;
  label: string;
  templates: T[];
}

/** Templates grouped by category in the enum's order, unknown categories last, names A to Z inside. */
export function groupByCategory<T extends TemplateLike>(templates: readonly T[]): CategoryGroup<T>[] {
  const map = new Map<number, T[]>();
  for (const t of templates) {
    const key = CATEGORY_LABELS[t.category] ? t.category : 0;
    map.set(key, [...(map.get(key) ?? []), t]);
  }
  return [...map.entries()]
    .sort(([a], [b]) => (a || 99) - (b || 99))
    .map(([category, list]) => ({
      category,
      label: CATEGORY_LABELS[category] ?? 'Other',
      templates: [...list].sort((x, y) => x.name.localeCompare(y.name)),
    }));
}

/** "Trend · Advanced". */
export function templateMeta(t: Pick<TemplateLike, 'category' | 'difficulty'>): string {
  return [CATEGORY_LABELS[t.category], DIFFICULTY_LABELS[t.difficulty]].filter(Boolean).join(' · ');
}
