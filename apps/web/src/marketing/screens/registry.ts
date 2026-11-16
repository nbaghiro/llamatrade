import type { ComponentType } from 'react';

import { BacktestScreen } from './BacktestScreen';
import { CopilotScreen } from './CopilotScreen';
import { EditorScreen } from './EditorScreen';
import { BrokerScreen, StrategiesScreen, TemplatesScreen, TradesScreen } from './LibraryScreens';
import { ChecksScreen, OrdersScreen, ReconScreen } from './LiveScreens';
import { CopilotPhone, HomePhone, PortfolioPhone, StrategyPhone } from './PhoneScreens';
import { PortfolioScreen } from './PortfolioScreen';
import { SessionScreen } from './SessionScreen';

export type ScreenName =
  | 'backtest'
  | 'editor'
  | 'portfolio'
  | 'copilot'
  | 'session'
  | 'templates'
  | 'strategies'
  | 'trades'
  | 'broker'
  | 'checks'
  | 'orders'
  | 'recon';

export type PhoneName = 'home' | 'strategy' | 'portfolio' | 'copilot';

export const SCREENS: Record<ScreenName, { title: string; Component: ComponentType }> = {
  backtest: { title: 'Backtest · Recession Radar', Component: BacktestScreen },
  editor: { title: 'Strategy editor', Component: EditorScreen },
  portfolio: { title: 'Portfolio', Component: PortfolioScreen },
  copilot: { title: 'Copilot', Component: CopilotScreen },
  session: { title: 'Live session · Tech Momentum Rotation', Component: SessionScreen },
  templates: { title: 'Templates', Component: TemplatesScreen },
  strategies: { title: 'Strategies', Component: StrategiesScreen },
  trades: { title: 'Backtest trades', Component: TradesScreen },
  broker: { title: 'Broker connection', Component: BrokerScreen },
  checks: { title: 'Risk checks', Component: ChecksScreen },
  orders: { title: 'Order stream', Component: OrdersScreen },
  recon: { title: 'Reconciliation', Component: ReconScreen },
};

export const PHONES: Record<PhoneName, ComponentType> = {
  home: HomePhone,
  strategy: StrategyPhone,
  portfolio: PortfolioPhone,
  copilot: CopilotPhone,
};
