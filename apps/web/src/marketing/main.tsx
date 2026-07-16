import React from 'react';
import ReactDOM from 'react-dom/client';

import MarketingPage from './MarketingPage';
import './marketing-base.css';

/**
 * Standalone marketing entry — the marketing-only build (`npm run build:marketing`
 * → dist-marketing/), deployed as its own static site. The very same
 * <MarketingPage/> also renders at "/" inside the app (see src/App.tsx); this
 * mounts it by itself, with no router, no stores, and no gRPC clients.
 */
ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <MarketingPage />
  </React.StrictMode>,
);
