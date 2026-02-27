// Strategy API Response Types
// These match the backend services/strategy/src/models.py schemas

// Enums matching backend
export type StrategyType = 'trend_following' | 'mean_reversion' | 'momentum' | 'breakout' | 'custom';
export type StrategyStatus = 'draft' | 'active' | 'paused' | 'archived';
export type DeploymentStatus = 'pending' | 'running' | 'paused' | 'stopped' | 'error';
export type DeploymentEnvironment = 'paper' | 'live';
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

export interface DeploymentCreate {
  version?: number;
  environment: DeploymentEnvironment;
  config_override?: DeploymentConfigOverride;
}

export interface DeploymentConfigOverride {
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

export interface DeploymentResponse {
  id: string;
  strategy_id: string;
  version: number;
  environment: DeploymentEnvironment;
  status: DeploymentStatus;
  started_at: string | null;
  stopped_at: string | null;
  config_override: DeploymentConfigOverride | null;
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
