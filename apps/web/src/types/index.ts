// Common types
import { StrategyStatus } from '../generated/proto/strategy_pb';

export interface User {
  id: string;
  email: string;
  roles: string[];
  tenant_id: string;
  created_at: string;
}

export interface Strategy {
  id: string;
  name: string;
  description: string | null;
  strategy_type: string;
  status: StrategyStatus;
  current_version: number;
  created_at: string;
  updated_at: string;
}

export interface BacktestResult {
  id: string;
  backtest_id: string;
  metrics: BacktestMetrics;
  equity_curve: EquityPoint[];
  trades: Trade[];
  created_at: string;
}

export interface BacktestMetrics {
  total_return: number;
  annual_return: number;
  sharpe_ratio: number;
  sortino_ratio: number;
  max_drawdown: number;
  win_rate: number;
  profit_factor: number;
  total_trades: number;
}

export interface EquityPoint {
  date: string;
  equity: number;
  drawdown: number;
}

export interface Trade {
  entry_date: string;
  exit_date: string | null;
  symbol: string;
  side: 'long' | 'short';
  entry_price: number;
  exit_price: number | null;
  quantity: number;
  pnl: number;
  pnl_percent: number;
}

export interface Position {
  symbol: string;
  qty: number;
  side: string;
  cost_basis: number;
  market_value: number;
  unrealized_pnl: number;
  unrealized_pnl_percent: number;
  current_price: number;
}

export interface Order {
  id: string;
  symbol: string;
  side: 'buy' | 'sell';
  qty: number;
  order_type: string;
  status: string;
  filled_qty: number;
  filled_avg_price: number | null;
  submitted_at: string;
}
