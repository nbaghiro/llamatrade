/**
 * Strategy Templates - Type definitions
 *
 * Templates are fetched from backend API (single source of truth).
 * This file only contains display helpers for proto enum types.
 */

import {
  AssetClass,
  TemplateCategory,
  TemplateDifficulty,
} from '../generated/proto/strategy_pb';

// Re-export proto enums for convenience
export { AssetClass, TemplateCategory, TemplateDifficulty };

/**
 * Strategy template as returned by the backend API
 */
export interface StrategyTemplate {
  id: string;
  name: string;
  description: string;
  category: TemplateCategory;
  asset_class: AssetClass;
  config_sexpr: string;
  config_json: Record<string, unknown>;
  tags: string[];
  difficulty: TemplateDifficulty;
}

/**
 * Category display labels
 */
export const CATEGORY_LABELS: Record<TemplateCategory, string> = {
  [TemplateCategory.UNSPECIFIED]: 'Unknown',
  [TemplateCategory.BUY_AND_HOLD]: 'Buy & Hold',
  [TemplateCategory.TACTICAL]: 'Tactical',
  [TemplateCategory.FACTOR]: 'Factor',
  [TemplateCategory.INCOME]: 'Income',
  [TemplateCategory.TREND]: 'Trend',
  [TemplateCategory.MEAN_REVERSION]: 'Mean Reversion',
  [TemplateCategory.ALTERNATIVES]: 'Alternatives',
};

/**
 * All available categories (excluding UNSPECIFIED)
 */
export const ALL_CATEGORIES: TemplateCategory[] = [
  TemplateCategory.BUY_AND_HOLD,
  TemplateCategory.TACTICAL,
  TemplateCategory.FACTOR,
  TemplateCategory.INCOME,
  TemplateCategory.TREND,
  TemplateCategory.MEAN_REVERSION,
  TemplateCategory.ALTERNATIVES,
];

/**
 * Difficulty display labels
 */
export const DIFFICULTY_LABELS: Record<TemplateDifficulty, string> = {
  [TemplateDifficulty.UNSPECIFIED]: 'Unknown',
  [TemplateDifficulty.BEGINNER]: 'Beginner',
  [TemplateDifficulty.INTERMEDIATE]: 'Intermediate',
  [TemplateDifficulty.ADVANCED]: 'Advanced',
};

/**
 * All difficulty levels (excluding UNSPECIFIED)
 */
export const ALL_DIFFICULTIES: TemplateDifficulty[] = [
  TemplateDifficulty.BEGINNER,
  TemplateDifficulty.INTERMEDIATE,
  TemplateDifficulty.ADVANCED,
];
