import {
  Activity,
  Bell,
  CandlestickChart,
  FlaskConical,
  LineChart,
  User,
  Wallet,
} from 'lucide-react';
import type { ComponentType } from 'react';

import type { DestinationKey } from '../../lib/navigation';
import { CopilotMark } from '../common/Logo';

type DestinationIcon = ComponentType<{ className?: string; strokeWidth?: number | string }>;

export const DESTINATION_ICON: Record<DestinationKey, DestinationIcon> = {
  home: CopilotMark,
  markets: CandlestickChart,
  portfolio: Wallet,
  strategies: LineChart,
  backtests: FlaskConical,
  sessions: Activity,
  activity: Bell,
  account: User,
};
