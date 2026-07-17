import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { useEffect } from 'react';

import ActiveStrategies from '../../components/dashboard/ActiveStrategies';
import ChartHero from '../../components/dashboard/ChartHero';
import CopilotHero from '../../components/dashboard/CopilotHero';
import KpiRail from '../../components/dashboard/KpiRail';
import MarketStatusPill from '../../components/dashboard/MarketStatusPill';
import QuickActions from '../../components/dashboard/QuickActions';
import RecentActivity from '../../components/dashboard/RecentActivity';
import { useAuthStore } from '../../store/auth';

function greetingWord(hour: number): string {
  if (hour < 12) return 'Good morning';
  if (hour < 18) return 'Good afternoon';
  return 'Good evening';
}

function displayName(user: { firstName?: string; email?: string } | null | undefined): string {
  if (user?.firstName) return user.firstName;
  const email = user?.email;
  if (!email) return 'trader';
  const handle = email.split('@')[0].split(/[.\-_]/)[0];
  return handle.charAt(0).toUpperCase() + handle.slice(1);
}

export default function DashboardPage() {
  const fetchDashboard = useDashboardStore((s) => s.fetchDashboard);
  const fetchMarketStatus = useDashboardStore((s) => s.fetchMarketStatus);
  const liveStrategiesCount = useDashboardStore((s) => s.liveStrategiesCount);
  const error = useDashboardStore((s) => s.error);
  const user = useAuthStore((s) => s.user);

  useEffect(() => {
    fetchDashboard();
    const id = setInterval(fetchMarketStatus, 60_000);
    return () => clearInterval(id);
  }, [fetchDashboard, fetchMarketStatus]);

  const now = new Date();
  const subtitle = `${now.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
  })} · ${liveStrategiesCount > 0 ? 'machine running' : 'machine idle'}`;

  return (
    <div className="bg-bone bg-grid min-h-[calc(100vh-56px)]">
      <div className="max-w-[1760px] mx-auto px-6 lg:px-8 py-6 pb-16">
        <div className="flex items-baseline justify-between gap-4 mb-4 flex-wrap">
          <div className="flex items-baseline gap-3.5 flex-wrap">
            <h1 className="font-display uppercase text-[34px] leading-[0.92] tracking-[0.01em]">
              {greetingWord(now.getHours())}, {displayName(user)}.
            </h1>
            <span className="font-mono text-[11.5px] text-ink/55">{subtitle}</span>
          </div>
          <MarketStatusPill />
        </div>

        {error && (
          <div className="mb-4 border-2 border-ink bg-orange-500 px-4 py-2 font-mono text-[11px] font-bold uppercase tracking-[0.06em] text-ink">
            {error}
          </div>
        )}

        <div className="mb-4">
          <QuickActions />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[0.72fr_2fr_1.1fr] gap-4 mb-4">
          <KpiRail />
          <ChartHero />
          <CopilotHero />
        </div>

        <div className="grid grid-cols-1 lg:grid-cols-[1.55fr_1fr] gap-4">
          <ActiveStrategies />
          <RecentActivity />
        </div>
      </div>
    </div>
  );
}
