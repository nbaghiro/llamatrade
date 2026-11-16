import {
  FlaskConical,
  Home,
  LineChart,
  Sparkles,
  Timer,
  User,
  Wallet,
  type LucideIcon,
} from 'lucide-react';

import type { DestinationKey } from '../../lib/navigation';

export const DESTINATION_ICON: Record<DestinationKey, LucideIcon> = {
  home: Home,
  portfolio: Wallet,
  strategies: LineChart,
  backtests: FlaskConical,
  sessions: Timer,
  copilot: Sparkles,
  account: User,
};
