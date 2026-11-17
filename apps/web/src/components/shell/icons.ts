import {
  Activity,
  Bell,
  CandlestickChart,
  FlaskConical,
  Home,
  LineChart,
  Sparkles,
  User,
  Wallet,
  type LucideIcon,
} from 'lucide-react';

import type { DestinationKey } from '../../lib/navigation';

export const DESTINATION_ICON: Record<DestinationKey, LucideIcon> = {
  home: Home,
  markets: CandlestickChart,
  portfolio: Wallet,
  strategies: LineChart,
  backtests: FlaskConical,
  sessions: Activity,
  copilot: Sparkles,
  activity: Bell,
  account: User,
};
