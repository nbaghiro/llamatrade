import MarketingPage from './MarketingPage';

/**
 * Standalone marketing app root. This deploy is marketing ONLY — there is no
 * router, no auth store, and no gRPC clients here. It renders the single
 * landing page (a hash-anchor single-page site) directly.
 */
export default function App() {
  return <MarketingPage />;
}
