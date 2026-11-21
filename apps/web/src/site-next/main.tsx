import React from 'react';
import ReactDOM from 'react-dom/client';

import './site.css';
import SitePage from './SitePage';

ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <SitePage />
  </React.StrictMode>
);
