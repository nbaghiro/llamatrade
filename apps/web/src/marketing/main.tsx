import React from 'react';
import ReactDOM from 'react-dom/client';

import MarketingPage from './MarketingPage';
import './marketing-base.css';

/** Standalone entry for `npm run build:marketing`: the marketing page alone, no router or RPC clients. */
ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <MarketingPage />
  </React.StrictMode>
);
