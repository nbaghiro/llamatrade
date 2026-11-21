import { useEffect, useState } from 'react';
import { NavLink } from 'react-router-dom';

import { OPTIONS } from './options';

type Mode = 'light' | 'dark';

export function Switcher() {
  const [mode, setMode] = useState<Mode>(
    () => (document.documentElement.getAttribute('data-mode') as Mode | null) ?? 'dark'
  );
  useEffect(() => {
    const d = document.documentElement;
    d.setAttribute('data-mode', mode);
    d.setAttribute('data-acc', 'neutral');
  }, [mode]);
  return (
    <div className="fixed bottom-4 left-4 z-[100] flex items-center gap-1 rounded-full border border-line bg-panel p-1 text-xs shadow-lg">
      {OPTIONS.map((o) => (
        <NavLink
          key={o.id}
          to={`/${o.id}`}
          className={({ isActive }) =>
            `grid h-7 w-7 place-items-center rounded-full font-medium ${isActive ? 'bg-fg text-canvas' : 'text-fg-2'}`
          }
        >
          {o.label}
        </NavLink>
      ))}
      <button
        type="button"
        onClick={() => setMode(mode === 'dark' ? 'light' : 'dark')}
        className="h-7 rounded-full px-3 text-fg-2"
      >
        {mode === 'dark' ? 'Light' : 'Dark'}
      </button>
    </div>
  );
}
