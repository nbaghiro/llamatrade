/**
 * Strategy Templates - Type definitions
 *
 * Templates are fetched from backend API (single source of truth).
 * This file only contains type definitions used by the frontend.
 */

/**
 * Template Category - Primary classification by investment approach
 */
export type TemplateCategory =
  | 'buy-and-hold'
  | 'tactical'
  | 'factor'
  | 'income'
  | 'trend'
  | 'mean-reversion'
  | 'alternatives';

/**
 * Asset Class - What the strategy primarily invests in
 */
export type AssetClass =
  | 'equity'
  | 'fixed-income'
  | 'multi-asset'
  | 'crypto'
  | 'commodity'
  | 'options';

export type TemplateDifficulty = 'beginner' | 'intermediate' | 'advanced';

/**
 * Strategy template as returned by the backend API
 */
export interface StrategyTemplate {
  id: string;
  name: string;
  description: string;
  strategy_type: string;
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
  'buy-and-hold': 'Buy & Hold',
  tactical: 'Tactical',
  factor: 'Factor',
  income: 'Income',
  trend: 'Trend',
  'mean-reversion': 'Mean Reversion',
  alternatives: 'Alternatives',
};

/**
 * All available categories
 */
export const ALL_CATEGORIES: TemplateCategory[] = [
  'buy-and-hold',
  'tactical',
  'factor',
  'income',
  'trend',
  'mean-reversion',
  'alternatives',
];

/**
 * Difficulty display labels
 */
export const DIFFICULTY_LABELS: Record<TemplateDifficulty, string> = {
  beginner: 'Beginner',
  intermediate: 'Intermediate',
  advanced: 'Advanced',
};

/**
 * All difficulty levels
 */
export const ALL_DIFFICULTIES: TemplateDifficulty[] = ['beginner', 'intermediate', 'advanced'];
