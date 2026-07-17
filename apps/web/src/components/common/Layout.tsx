import { CreditCard, LineChart, FlaskConical, ChevronDown, LogOut, PieChart, Sparkles, User, Wallet } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Outlet, NavLink, useNavigate, useLocation } from 'react-router-dom';


import NewStrategyDialog from '../../components/strategies/NewStrategyDialog';
import StrategyPreviewDialog from '../../components/strategies/StrategyPreviewDialog';
import { useAuthStore } from '../../store/auth';
import { useBillingStore } from '@llamatrade/core/stores/billing';
import { useUIStore } from '../../store/ui';
import { AgentFAB } from '../agent/AgentFAB';
import { CopilotSidePanel } from '../agent/CopilotSidePanel';

import { Avatar } from './Avatar';
import { Logo } from './Logo';

const navItems = [
  { to: '/portfolio', icon: PieChart, label: 'Portfolio' },
  { to: '/strategies', icon: LineChart, label: 'Strategies' },
  { to: '/backtest', icon: FlaskConical, label: 'Backtest' },
  { to: '/copilot', icon: Sparkles, label: 'Copilot' },
];

export default function Layout() {
  const navigate = useNavigate();
  const location = useLocation();
  const logout = useAuthStore((state) => state.logout);
  const user = useAuthStore((state) => state.user);
  const [userMenuOpen, setUserMenuOpen] = useState(false);

  const { subscription, fetchSubscription } = useBillingStore();
  const { newStrategyDialogOpen, openNewStrategyDialog, closeNewStrategyDialog } = useUIStore();

  useEffect(() => {
    fetchSubscription();
  }, [fetchSubscription]);

  const handleLogout = () => {
    logout();
    navigate('/');
  };

  const planName = subscription?.plan?.name || 'Free Plan';

  return (
    <div className="min-h-screen bg-bone">
      <header className="h-14 bg-paper border-b-2 border-ink px-4 flex items-center justify-between">
        <div className="flex items-center gap-1">
          {/* Logo toggle (mirrors Galleo's in-app logo → marketing hop):
              the first click from anywhere in the app lands on the dashboard
              (client-side); a second click while already on the dashboard
              escapes to the marketing page at "/home" (a real web route that
              always renders <MarketingPage/>, see App.tsx). The href stays
              "/home" so modifier / middle clicks still open it in a new tab. */}
          <a
            href="/home"
            className="px-3 py-2 mr-4"
            onClick={(e) => {
              // Defer modifier / non-primary clicks to the browser (open in a
              // new tab, etc.) as a real navigation to /home.
              if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
              // Not on the dashboard yet → go there first (client-side).
              if (location.pathname !== '/dashboard') {
                e.preventDefault();
                navigate('/dashboard');
              }
              // Already on the dashboard → fall through to the real /home nav.
            }}
          >
            <Logo size={28} showText />
          </a>

          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-2 nav-link ${isActive ? 'nav-link-active' : ''}`
              }
            >
              <item.icon className="w-4 h-4" />
              <span>{item.label}</span>
            </NavLink>
          ))}

          <div className="ml-2">
            <button
              onClick={openNewStrategyDialog}
              className="btn btn-secondary btn-sm"
            >
              <span>Create</span>
              <ChevronDown className="w-4 h-4" />
            </button>
          </div>

        </div>

        <div className="flex items-center gap-2">
          <NavLink
            to="/wallet"
            title="Wallet"
            aria-label="Wallet"
            className={({ isActive }) =>
              `grid h-9 w-9 place-items-center border-2 transition-colors ${
                isActive
                  ? 'border-ink bg-orange-500 text-ink'
                  : 'border-transparent text-ink/60 hover:bg-ink/5 hover:text-ink'
              }`
            }
          >
            <Wallet className="h-[18px] w-[18px]" />
          </NavLink>

          <div className="relative">
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center gap-1 p-1.5 hover:bg-ink/5 transition-colors"
            >
              <Avatar
                avatarUrl={user?.avatarUrl}
                firstName={user?.firstName}
                lastName={user?.lastName}
                email={user?.email}
                size={32}
              />
              <ChevronDown className={`w-3.5 h-3.5 text-ink/50 transition-transform ${userMenuOpen ? 'rotate-180' : ''}`} />
            </button>

            {userMenuOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setUserMenuOpen(false)}
                />
                <div className="dropdown right-0 top-full mt-2 w-56">
                  <div className="px-4 py-3 border-b-2 border-ink">
                    <p className="text-sm font-medium text-ink truncate">{user?.email}</p>
                    <p className="text-[11px] font-mono uppercase tracking-wide text-ink/60 mt-1">{planName}</p>
                  </div>
                  <NavLink
                    to="/settings"
                    onClick={() => setUserMenuOpen(false)}
                    className="dropdown-item"
                  >
                    <User className="w-4 h-4" />
                    Settings
                  </NavLink>
                  <NavLink
                    to="/billing"
                    onClick={() => setUserMenuOpen(false)}
                    className="dropdown-item"
                  >
                    <CreditCard className="w-4 h-4" />
                    Manage Billing
                  </NavLink>
                  <button
                    onClick={handleLogout}
                    className="dropdown-item w-full"
                  >
                    <LogOut className="w-4 h-4" />
                    Log out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      <main>
        <Outlet />
      </main>

      <AgentFAB />
      <CopilotSidePanel />

      <NewStrategyDialog isOpen={newStrategyDialogOpen} onClose={closeNewStrategyDialog} />

      <StrategyPreviewDialog />
    </div>
  );
}
