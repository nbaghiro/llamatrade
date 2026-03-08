import { CreditCard, LineChart, FlaskConical, ChevronDown, LogOut, User, Wallet } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Outlet, NavLink, useNavigate } from 'react-router-dom';

import NewStrategyDialog from '../../components/strategies/NewStrategyDialog';
import { useAuthStore } from '../../store/auth';
import { useBillingStore } from '../../store/billing';
import { useUIStore } from '../../store/ui';

import Logo from './Logo';
import { ThemeToggle } from './ThemeToggle';

const navItems = [
  { to: '/portfolio', icon: Wallet, label: 'Portfolio' },
  { to: '/strategies', icon: LineChart, label: 'Strategies' },
  { to: '/backtest', icon: FlaskConical, label: 'Backtest' },
];

export default function Layout() {
  const navigate = useNavigate();
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
    navigate('/login');
  };

  const planName = subscription?.plan?.name || 'Free Plan';

  return (
    <div className="min-h-screen bg-gray-50 dark:bg-gray-950">
      {/* Top Navigation Bar */}
      <header className="h-14 bg-white dark:bg-gray-900 border-b border-gray-200 dark:border-gray-800 px-4 flex items-center justify-between">
        {/* Left: Logo + Nav */}
        <div className="flex items-center gap-1">
          {/* Logo */}
          <NavLink to="/portfolio" className="px-3 py-2 mr-4">
            <Logo size={28} showText />
          </NavLink>

          {/* Main Nav Items */}
          {navItems.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              className={({ isActive }) =>
                `flex items-center gap-2 px-3 py-2 text-sm font-medium rounded-lg transition-colors ${
                  isActive
                    ? 'text-gray-900 dark:text-gray-100 bg-gray-100 dark:bg-gray-800'
                    : 'text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-gray-100 hover:bg-gray-50 dark:hover:bg-gray-800'
                }`
              }
            >
              <item.icon className="w-4 h-4" />
              <span>{item.label}</span>
            </NavLink>
          ))}

          {/* Create Button */}
          <div className="ml-2">
            <button
              onClick={openNewStrategyDialog}
              className="flex items-center gap-1.5 px-3 py-1.5 text-sm font-medium text-gray-600 dark:text-gray-400 bg-gray-100 dark:bg-gray-800 rounded-full hover:bg-gray-200 dark:hover:bg-gray-700 transition-colors"
            >
              <span>Create</span>
              <ChevronDown className="w-4 h-4" />
            </button>
          </div>
        </div>

        {/* Right: User Menu */}
        <div className="flex items-center gap-3">
          <div className="relative">
            <button
              onClick={() => setUserMenuOpen(!userMenuOpen)}
              className="flex items-center gap-2 p-1.5 rounded-full hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
            >
              <img
                src="https://images.unsplash.com/photo-1438761681033-6461ffad8d80?w=80&h=80&fit=crop&crop=face"
                alt="Profile"
                className="w-8 h-8 rounded-full object-cover"
              />
            </button>

            {/* User Dropdown */}
            {userMenuOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setUserMenuOpen(false)}
                />
                <div className="absolute right-0 top-full mt-2 w-56 bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded-lg shadow-dropdown z-50 py-1">
                  <div className="px-4 py-3 border-b border-gray-100 dark:border-gray-800">
                    <p className="text-sm font-medium text-gray-900 dark:text-gray-100">{user?.email}</p>
                    <p className="text-xs text-gray-500 dark:text-gray-400 mt-0.5">{planName}</p>
                  </div>
                  <NavLink
                    to="/settings"
                    onClick={() => setUserMenuOpen(false)}
                    className="flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    <User className="w-4 h-4 text-gray-400" />
                    Settings
                  </NavLink>
                  <NavLink
                    to="/billing"
                    onClick={() => setUserMenuOpen(false)}
                    className="flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    <CreditCard className="w-4 h-4 text-gray-400" />
                    Manage Billing
                  </NavLink>
                  <button
                    onClick={handleLogout}
                    className="w-full flex items-center gap-3 px-4 py-2.5 text-sm text-gray-700 dark:text-gray-300 hover:bg-gray-50 dark:hover:bg-gray-800"
                  >
                    <LogOut className="w-4 h-4 text-gray-400" />
                    Log out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main>
        <Outlet />
      </main>

      {/* Floating Theme Toggle */}
      <ThemeToggle />

      {/* New Strategy Dialog (global - works from any page) */}
      <NewStrategyDialog isOpen={newStrategyDialogOpen} onClose={closeNewStrategyDialog} />
    </div>
  );
}
