import { lazy } from 'react';

export const OPTIONS = [
  { id: 'c', label: 'C', App: lazy(() => import('./c/App')) },
  { id: 'd', label: 'D', App: lazy(() => import('./d/App')) },
  { id: 'e', label: 'E', App: lazy(() => import('./e/App')) },
  { id: 'f', label: 'F', App: lazy(() => import('./f/App')) },
  { id: 'g', label: 'G', App: lazy(() => import('./g/App')) },
  { id: 'h', label: 'H', App: lazy(() => import('./h/App')) },
  { id: 'i', label: 'I', App: lazy(() => import('./i/App')) },
  { id: 'j', label: 'J', App: lazy(() => import('./j/App')) },
  { id: 'k', label: 'K', App: lazy(() => import('./k/App')) },
] as const;
