import { LayoutGrid, Play, Plus } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

import { useUIStore } from '../../store/ui';

interface Action {
  title: string;
  detail: string;
  icon: typeof Plus;
  onClick: () => void;
  primary?: boolean;
}

export default function QuickActions() {
  const navigate = useNavigate();
  const openNewStrategyDialog = useUIStore((s) => s.openNewStrategyDialog);

  const actions: Action[] = [
    {
      title: 'New Strategy',
      detail: 'Blocks or DSL editor',
      icon: Plus,
      onClick: openNewStrategyDialog,
      primary: true,
    },
    { title: 'Run Backtest', detail: 'Test against history', icon: Play, onClick: () => navigate('/backtest') },
    { title: 'Templates', detail: 'Proven starting points', icon: LayoutGrid, onClick: openNewStrategyDialog },
  ];

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
      {actions.map((a) => (
        <button
          key={a.title}
          onClick={a.onClick}
          className={`border-2 border-ink shadow-[4px_4px_0_#0d0d0d] px-4 py-4 flex items-center gap-3.5 text-left transition-transform hover:-translate-y-0.5 ${
            a.primary ? 'bg-orange-500' : 'bg-paper'
          }`}
        >
          <span
            className={`w-9 h-9 border-2 border-ink grid place-items-center shrink-0 ${
              a.primary ? 'bg-ink' : 'bg-paper'
            }`}
          >
            <a.icon className={`w-5 h-5 ${a.primary ? 'text-bone' : 'text-ink'}`} strokeWidth={2.2} />
          </span>
          <div>
            <div className="font-mono text-[13px] font-bold uppercase tracking-[0.04em]">{a.title}</div>
            <div className="font-mono text-[9.5px] uppercase tracking-[0.06em] text-ink/55 mt-0.5">
              {a.detail}
            </div>
          </div>
        </button>
      ))}
    </div>
  );
}
