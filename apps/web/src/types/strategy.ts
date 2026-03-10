// Strategy API Response Types
// These match the backend services/strategy/src/models.py schemas

// Import enum types from proto-generated code (single source of truth)
// Used within this file for display helpers and type definitions
import {
  ExecutionMode,
  ExecutionStatus,
} from '../generated/proto/common_pb';
import {
  AssetClass,
  IndicatorType,
  StrategyStatus,
  TemplateCategory,
  TemplateDifficulty,
} from '../generated/proto/strategy_pb';

// ============================================
// Enum Display Helpers
// ============================================

export function getStrategyStatusLabel(status: StrategyStatus): string {
  switch (status) {
    case StrategyStatus.DRAFT:
      return 'Draft';
    case StrategyStatus.ACTIVE:
      return 'Active';
    case StrategyStatus.PAUSED:
      return 'Paused';
    case StrategyStatus.ARCHIVED:
      return 'Archived';
    default:
      return 'Unknown';
  }
}

export function getExecutionStatusLabel(status: ExecutionStatus): string {
  switch (status) {
    case ExecutionStatus.PENDING:
      return 'Pending';
    case ExecutionStatus.RUNNING:
      return 'Running';
    case ExecutionStatus.PAUSED:
      return 'Paused';
    case ExecutionStatus.STOPPED:
      return 'Stopped';
    case ExecutionStatus.ERROR:
      return 'Error';
    default:
      return 'Unknown';
  }
}

export function getExecutionModeLabel(mode: ExecutionMode): string {
  switch (mode) {
    case ExecutionMode.PAPER:
      return 'Paper';
    case ExecutionMode.LIVE:
      return 'Live';
    default:
      return 'Unknown';
  }
}

export function getTemplateCategoryLabel(category: TemplateCategory): string {
  switch (category) {
    case TemplateCategory.BUY_AND_HOLD:
      return 'Buy & Hold';
    case TemplateCategory.TACTICAL:
      return 'Tactical';
    case TemplateCategory.FACTOR:
      return 'Factor';
    case TemplateCategory.INCOME:
      return 'Income';
    case TemplateCategory.TREND:
      return 'Trend';
    case TemplateCategory.MEAN_REVERSION:
      return 'Mean Reversion';
    case TemplateCategory.ALTERNATIVES:
      return 'Alternatives';
    default:
      return 'Unknown';
  }
}

export function getAssetClassLabel(assetClass: AssetClass): string {
  switch (assetClass) {
    case AssetClass.EQUITY:
      return 'Equity';
    case AssetClass.FIXED_INCOME:
      return 'Fixed Income';
    case AssetClass.MULTI_ASSET:
      return 'Multi-Asset';
    case AssetClass.CRYPTO:
      return 'Crypto';
    case AssetClass.COMMODITY:
      return 'Commodity';
    case AssetClass.OPTIONS:
      return 'Options';
    default:
      return 'Unknown';
  }
}

export function getIndicatorTypeLabel(indicator: IndicatorType): string {
  switch (indicator) {
    case IndicatorType.SMA:
      return 'SMA';
    case IndicatorType.EMA:
      return 'EMA';
    case IndicatorType.MACD:
      return 'MACD';
    case IndicatorType.ADX:
      return 'ADX';
    case IndicatorType.RSI:
      return 'RSI';
    case IndicatorType.STOCHASTIC:
      return 'Stochastic';
    case IndicatorType.CCI:
      return 'CCI';
    case IndicatorType.WILLIAMS_R:
      return "Williams %R";
    case IndicatorType.BOLLINGER_BANDS:
      return 'Bollinger Bands';
    case IndicatorType.ATR:
      return 'ATR';
    case IndicatorType.KELTNER_CHANNEL:
      return 'Keltner Channel';
    case IndicatorType.OBV:
      return 'OBV';
    case IndicatorType.MFI:
      return 'MFI';
    case IndicatorType.VWAP:
      return 'VWAP';
    case IndicatorType.DONCHIAN_CHANNEL:
      return 'Donchian Channel';
    default:
      return 'Unknown';
  }
}

export function getTemplateDifficultyLabel(difficulty: TemplateDifficulty): string {
  switch (difficulty) {
    case TemplateDifficulty.BEGINNER:
      return 'Beginner';
    case TemplateDifficulty.INTERMEDIATE:
      return 'Intermediate';
    case TemplateDifficulty.ADVANCED:
      return 'Advanced';
    default:
      return 'Unknown';
  }
}

// IndicatorCategory is UI-only categorization for display purposes
export type IndicatorCategory = 'trend' | 'momentum' | 'volatility' | 'volume' | 'channel';

// Request schemas
export interface StrategyCreate {
  name: string;
  description?: string;
  config_sexpr: string;
}

export interface StrategyUpdate {
  name?: string;
  description?: string;
  status?: StrategyStatus;
  config_sexpr?: string;
}

export interface ExecutionCreate {
  version?: number;
  mode: ExecutionMode;
  config_override?: ExecutionConfigOverride;
}

export interface ExecutionConfigOverride {
  symbols?: string[];
  timeframe?: string;
  stop_loss_pct?: number;
  take_profit_pct?: number;
  sizing_type?: string;
  sizing_value?: number;
}

// Response schemas
export interface StrategyResponse {
  id: string;
  name: string;
  description: string | null;
  status: StrategyStatus;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface StrategyConfigJSON {
  name?: string;
  symbols: string[];
  timeframe: string;
  entry?: unknown;
  exit?: unknown;
  position_size_pct?: number;
  stop_loss_pct?: number;
  take_profit_pct?: number;
  trailing_stop_pct?: number;
}

export interface StrategyDetailResponse extends StrategyResponse {
  config_sexpr: string;
  config_json: StrategyConfigJSON;
  symbols: string[];
  timeframe: string;
  ui_state?: Record<string, unknown>; // Block tree for visual builder
}

export interface StrategyVersionResponse {
  version: number;
  config_sexpr: string;
  config_json: StrategyConfigJSON;
  symbols: string[];
  timeframe: string;
  changelog: string | null;
  created_at: string;
}

export interface ExecutionResponse {
  id: string;
  strategy_id: string;
  version: number;
  mode: ExecutionMode;
  status: ExecutionStatus;
  started_at: string | null;
  stopped_at: string | null;
  config_override: ExecutionConfigOverride | null;
  error_message: string | null;
  created_at: string;
}

export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings: string[];
}

export interface TemplateResponse {
  id: string;
  name: string;
  description: string | null;
  category: TemplateCategory;
  asset_class: AssetClass;
  config_sexpr: string;
  config_json: StrategyConfigJSON;
  tags: string[];
  difficulty: TemplateDifficulty;
}

export interface IndicatorParam {
  name: string;
  type: 'int' | 'float' | 'str';
  default: number | string | null;
  min?: number;
  max?: number;
  description: string;
}

export interface IndicatorInfoResponse {
  type: IndicatorType;
  name: string;
  description: string;
  category: IndicatorCategory;
  params: IndicatorParam[];
  outputs: string[];
}

// Pagination
export interface PaginatedResponse<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

// List query params
export interface StrategyListParams {
  page?: number;
  page_size?: number;
  status?: StrategyStatus;
}

export interface TemplateListParams {
  category?: TemplateCategory;
  asset_class?: AssetClass;
  difficulty?: TemplateDifficulty;
}

export interface IndicatorListParams {
  category?: IndicatorCategory;
}
