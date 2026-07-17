import { useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';

import Layout from './components/common/Layout';
import MarketingPage from './marketing/MarketingPage';
import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import BillingPage from './pages/billing/BillingPage';
import PaymentMethodsPage from './pages/billing/PaymentMethodsPage';
import SubscribePage from './pages/billing/SubscribePage';
import CopilotPage from './pages/copilot/CopilotPage';
import DashboardPage from './pages/dashboard/DashboardPage';
import PortfolioPage from './pages/portfolio/PortfolioPage';
import SettingsPage from './pages/settings/SettingsPage';
import StrategiesPage from './pages/strategies/StrategiesPage';
import StrategyEditorPage from './pages/strategies/StrategyEditorPage';
import TemplatesPage from './pages/strategies/TemplatesPage';
import BacktestPage from './pages/trading/BacktestPage';
import TradingPage from './pages/trading/TradingPage';
import WalletPage from './pages/wallet/WalletPage';
import { isTokenExpired, useAuthStore } from './store/auth';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const accessToken = useAuthStore((state) => state.accessToken);
  const logout = useAuthStore((state) => state.logout);

  // An expired token still reads as "authenticated" from persisted storage; drop
  // the stale session so the user re-authenticates instead of seeing empty pages.
  const expired = isTokenExpired(accessToken);
  useEffect(() => {
    if (isAuthenticated && expired) logout();
  }, [isAuthenticated, expired, logout]);

  if (!isAuthenticated || expired) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

/** Public "/" — the marketing page for visitors, the app for signed-in users. */
function PublicHome() {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const accessToken = useAuthStore((state) => state.accessToken);
  if (isAuthenticated && !isTokenExpired(accessToken)) {
    return <Navigate to="/dashboard" replace />;
  }
  return <MarketingPage />;
}

export default function App() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/" element={<PublicHome />} />
      {/* Always the marketing page — the in-app "escape hatch" (2nd logo click,
          see Layout) that lets even signed-in users view it. */}
      <Route path="/home" element={<MarketingPage />} />
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Protected app pages — pathless parent renders the app shell (Layout),
          children use absolute paths. `/` requires auth (unauthenticated users
          are redirected to /login by ProtectedRoute) and lands on the dashboard. */}
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/strategies" element={<StrategiesPage />} />
        <Route path="/strategies/templates" element={<TemplatesPage />} />
        <Route path="/strategies/builder" element={<StrategyEditorPage />} />
        <Route path="/strategies/:id" element={<StrategyEditorPage />} />
        <Route path="/backtest" element={<BacktestPage />} />
        <Route path="/copilot" element={<CopilotPage />} />
        <Route path="/trading" element={<TradingPage />} />
        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/wallet" element={<WalletPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/billing" element={<BillingPage />} />
        <Route path="/billing/subscribe" element={<SubscribePage />} />
        <Route path="/billing/payment-methods" element={<PaymentMethodsPage />} />
      </Route>

      {/* Fallback: send everything else to `/` (which resolves to the app or
          /login depending on auth). */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
