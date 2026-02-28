import { Routes, Route, Navigate } from 'react-router-dom';

import Layout from './components/common/Layout';
import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import BillingPage from './pages/billing/BillingPage';
import PaymentMethodsPage from './pages/billing/PaymentMethodsPage';
import SubscribePage from './pages/billing/SubscribePage';
import DashboardPage from './pages/dashboard/DashboardPage';
import PortfolioPage from './pages/portfolio/PortfolioPage';
import SettingsPage from './pages/settings/SettingsPage';
import { NewStrategyPage } from './pages/strategies/NewStrategyPage';
import StrategiesPage from './pages/strategies/StrategiesPage';
import StrategyEditorPage from './pages/strategies/StrategyEditorPage';
import BacktestPage from './pages/trading/BacktestPage';
import TradingPage from './pages/trading/TradingPage';
import { useAuthStore } from './store/auth';

function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}

export default function App() {
  return (
    <Routes>
      {/* Public routes */}
      <Route path="/login" element={<LoginPage />} />
      <Route path="/register" element={<RegisterPage />} />

      {/* Protected routes */}
      <Route
        path="/"
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route index element={<Navigate to="/dashboard" replace />} />
        <Route path="dashboard" element={<DashboardPage />} />
        <Route path="strategies" element={<StrategiesPage />} />
        <Route path="strategies/new" element={<NewStrategyPage />} />
        <Route path="strategies/builder" element={<StrategyEditorPage />} />
        <Route path="strategies/:id" element={<StrategyEditorPage />} />
        <Route path="backtest" element={<BacktestPage />} />
        <Route path="trading" element={<TradingPage />} />
        <Route path="portfolio" element={<PortfolioPage />} />
        <Route path="settings" element={<SettingsPage />} />
        <Route path="billing" element={<BillingPage />} />
        <Route path="billing/subscribe" element={<SubscribePage />} />
        <Route path="billing/payment-methods" element={<PaymentMethodsPage />} />
      </Route>

      {/* 404 */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
