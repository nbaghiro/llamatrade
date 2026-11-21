import { useEffect } from 'react';
import { Routes, Route, Navigate, useLocation } from 'react-router-dom';

import Layout from './components/common/Layout';
import MarketingPage from './marketing/MarketingPage';
import AlpacaCallbackPage from './pages/auth/AlpacaCallbackPage';
import CompleteSignupPage from './pages/auth/CompleteSignupPage';
import ForgotPasswordPage from './pages/auth/ForgotPasswordPage';
import LoginPage from './pages/auth/LoginPage';
import RegisterPage from './pages/auth/RegisterPage';
import ResetPasswordPage from './pages/auth/ResetPasswordPage';
import VerifyEmailPage from './pages/auth/VerifyEmailPage';
import BacktestComparePage from './pages/backtests/BacktestComparePage';
import BacktestHistoryPage from './pages/backtests/BacktestHistoryPage';
import BacktestRunPage from './pages/backtests/BacktestRunPage';
import PaymentMethodsPage from './pages/billing/PaymentMethodsPage';
import PlansPage from './pages/billing/PlansPage';
import ConnectAlpacaPage from './pages/connect/ConnectAlpacaPage';
import CopilotPage from './pages/copilot/CopilotPage';
import MarketsPage from './pages/markets/MarketsPage';
import NotificationsPage from './pages/notifications/NotificationsPage';
import WelcomePage from './pages/onboarding/WelcomePage';
import WelcomeResultPage from './pages/onboarding/WelcomeResultPage';
import WelcomeTemplatePage from './pages/onboarding/WelcomeTemplatePage';
import ActivityPage from './pages/portfolio/ActivityPage';
import ChecksPage from './pages/portfolio/ChecksPage';
import PortfolioPage from './pages/portfolio/PortfolioPage';
import SleevePage from './pages/portfolio/SleevePage';
import GoLivePage from './pages/sessions/GoLivePage';
import OrderCheckPage from './pages/sessions/OrderCheckPage';
import RebalancesPage from './pages/sessions/RebalancesPage';
import SessionPage from './pages/sessions/SessionPage';
import SettingsPage from './pages/settings/SettingsPage';
import StrategiesPage from './pages/strategies/StrategiesPage';
import StrategyDetailPage from './pages/strategies/StrategyDetailPage';
import StrategyEditorPage from './pages/strategies/StrategyEditorPage';
import StrategyVersionsPage from './pages/strategies/StrategyVersionsPage';
import TemplatesPage from './pages/strategies/TemplatesPage';
import BacktestPage from './pages/trading/BacktestPage';
import TradingPage from './pages/trading/TradingPage';
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

/** /copilot is Home's chat; any question or subject in the address goes along. */
function CopilotHome() {
  const { search } = useLocation();
  return <Navigate to={`/dashboard${search}`} replace />;
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
      <Route path="/forgot-password" element={<ForgotPasswordPage />} />
      <Route path="/reset-password" element={<ResetPasswordPage />} />
      <Route path="/verify-email" element={<VerifyEmailPage />} />
      {/* Alpaca OAuth returns (public): login handoff + sign-up completion. */}
      <Route path="/oauth/alpaca/callback" element={<AlpacaCallbackPage />} />
      <Route path="/signup/complete" element={<CompleteSignupPage />} />

      {/* Protected pages with their own top bar, outside the app shell. */}
      <Route
        path="/welcome"
        element={
          <ProtectedRoute>
            <WelcomePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/welcome/template/:id"
        element={
          <ProtectedRoute>
            <WelcomeTemplatePage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/welcome/result/:runId"
        element={
          <ProtectedRoute>
            <WelcomeResultPage />
          </ProtectedRoute>
        }
      />
      <Route
        path="/connect/alpaca"
        element={
          <ProtectedRoute>
            <ConnectAlpacaPage />
          </ProtectedRoute>
        }
      />

      {/* Protected app pages — pathless parent renders the app shell (Layout),
          children use absolute paths. */}
      <Route
        element={
          <ProtectedRoute>
            <Layout />
          </ProtectedRoute>
        }
      >
        <Route path="/dashboard" element={<CopilotPage />} />
        <Route path="/markets" element={<MarketsPage />} />

        <Route path="/strategies" element={<StrategiesPage />} />
        <Route path="/strategies/templates" element={<TemplatesPage />} />
        <Route path="/strategies/builder" element={<StrategyEditorPage />} />
        <Route path="/strategies/:id" element={<StrategyDetailPage />} />
        <Route path="/strategies/:id/edit" element={<StrategyEditorPage />} />
        <Route path="/strategies/:id/versions" element={<StrategyVersionsPage />} />
        <Route path="/strategies/:id/:tab" element={<StrategyDetailPage />} />

        <Route path="/backtest" element={<BacktestPage />} />
        <Route path="/backtest/:runId" element={<BacktestRunPage />} />
        <Route path="/backtests" element={<BacktestHistoryPage />} />
        <Route path="/backtests/compare" element={<BacktestComparePage />} />

        <Route path="/trading" element={<TradingPage />} />
        <Route path="/trading/orders/:orderId" element={<OrderCheckPage />} />
        <Route path="/trading/:sessionId" element={<SessionPage />} />
        <Route path="/trading/:sessionId/rebalances" element={<RebalancesPage />} />
        <Route path="/trading/:sessionId/live" element={<GoLivePage />} />
        <Route path="/sessions" element={<Navigate to="/trading" replace />} />

        <Route path="/portfolio" element={<PortfolioPage />} />
        <Route path="/portfolio/sleeves/:sleeveId" element={<SleevePage />} />
        <Route path="/portfolio/activity" element={<ActivityPage />} />
        <Route path="/portfolio/checks" element={<ChecksPage />} />
        <Route path="/wallet" element={<Navigate to="/portfolio/activity" replace />} />

        <Route path="/copilot" element={<CopilotHome />} />
        <Route path="/copilot/:sessionId" element={<CopilotPage />} />

        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/settings/plans" element={<PlansPage />} />
        <Route path="/settings/:section" element={<SettingsPage />} />
        <Route path="/notifications" element={<NotificationsPage />} />
        <Route path="/billing" element={<Navigate to="/settings/plan" replace />} />
        <Route path="/billing/subscribe" element={<PlansPage />} />
        <Route path="/billing/payment-methods" element={<PaymentMethodsPage />} />
      </Route>

      {/* Fallback: send everything else to `/` (which resolves to the app or
          /login depending on auth). */}
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
