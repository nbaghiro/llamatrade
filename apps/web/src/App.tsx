import { Routes, Route, Navigate } from 'react-router-dom';

import Layout from './components/Layout';
import BacktestPage from './pages/BacktestPage';
import BillingPage from './pages/BillingPage';
import DashboardPage from './pages/DashboardPage';
import LoginPage from './pages/LoginPage';
import PaymentMethodsPage from './pages/PaymentMethodsPage';
import PortfolioPage from './pages/PortfolioPage';
import RegisterPage from './pages/RegisterPage';
import SettingsPage from './pages/SettingsPage';
import StrategiesPage from './pages/StrategiesPage';
import StrategyEditorPage from './pages/StrategyEditorPage';
import SubscribePage from './pages/SubscribePage';
import TradingPage from './pages/TradingPage';
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
        <Route path="strategies/new" element={<StrategyEditorPage />} />
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
