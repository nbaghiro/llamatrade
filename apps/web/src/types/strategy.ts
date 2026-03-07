// Strategy API Response Types
// These match the backend services/strategy/src/models.py schemas

// Import enum types from proto-generated code (single source of truth)
import {
  ExecutionMode,
  ExecutionStatus,
} from '../generated/proto/common_pb';
import { StrategyStatus } from '../generated/proto/strategy_pb';

// Re-export proto enums for use in this module
export { StrategyStatus, ExecutionStatus, ExecutionMode };

// Trading approach type - describes the trading strategy's approach/philosophy
// This is a frontend-only concept derived from strategy configuration/tags
// Not defined in proto as it's UI categorization
export type TradingApproach = 'trend_following' | 'mean_reversion' | 'momentum' | 'breakout' | 'custom';

// StrategyType is used for trading approach categorization in the UI
export type StrategyType = TradingApproach;

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
export type IndicatorType =
  | 'sma'
  | 'ema'
  | 'macd'
  | 'adx'
  | 'rsi'
  | 'stochastic'
  | 'cci'
  | 'williams_r'
  | 'bollinger_bands'
  | 'atr'
  | 'keltner_channel'
  | 'obv'
  | 'mfi'
  | 'vwap'
  | 'donchian_channel';
export type IndicatorCategory = 'trend' | 'momentum' | 'volatility' | 'volume' | 'channel';
export type TemplateDifficulty = 'beginner' | 'intermediate' | 'advanced';

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
  strategy_type: StrategyType;
  status: StrategyStatus;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface StrategyConfigJSON {
  name?: string;
  type?: StrategyType;
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
  strategy_type: StrategyType;
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
  strategy_type?: StrategyType;
}

export interface TemplateListParams {
  strategy_type?: StrategyType;
  difficulty?: TemplateDifficulty;
}

export interface IndicatorListParams {
  category?: IndicatorCategory;
}
