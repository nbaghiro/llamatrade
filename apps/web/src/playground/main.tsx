import React, { Suspense } from 'react';
import ReactDOM from 'react-dom/client';
import { HashRouter, Navigate, Route, Routes } from 'react-router-dom';

import '../index.css';
import { OPTIONS } from './options';
import { Switcher } from './Switcher';

/** Design playground (playground.html): three directions on fixed demo data, no RPC clients. */
ReactDOM.createRoot(document.getElementById('root') as HTMLElement).render(
  <React.StrictMode>
    <HashRouter>
      <Suspense fallback={null}>
        <Routes>
          {OPTIONS.map((o) => (
            <Route key={o.id} path={`/${o.id}/*`} element={<o.App />} />
          ))}
          <Route path="*" element={<Navigate to="/c" replace />} />
        </Routes>
      </Suspense>
      <Switcher />
    </HashRouter>
  </React.StrictMode>
);
