import { useNavigate } from 'react-router-dom';

import { useDashboardStore, type ActivityKind, type DashboardActivity } from '../../store/dashboard';

import { timeAgo } from './format';

const TAG: Record<ActivityKind, { label: string; className: string }> = {
  buy: { label: 'Buy', className: 'bg-[#0f7a34] text-bone' },
  sell: { label: 'Sell', className: 'bg-[#c81e1e] text-bone' },
  backtest: { label: 'Test', className: 'bg-[#1a1aff] text-bone' },
  dividend: { label: 'Div', className: 'bg-orange-500 text-ink' },
};

function FeedRow({ item }: { item: DashboardActivity }) {
  const tag = TAG[item.kind];
  return (
    <div className="flex gap-3 px-4 py-2.5 border-b border-line last:border-b-0 items-start">
      <span
        className={`font-mono text-[9px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-0.5 shrink-0 mt-px ${tag.className}`}
      >
        {tag.label}
      </span>
      <div className="flex-1 min-w-0">
        <div className="text-[12.5px] font-semibold truncate">{item.title}</div>
        <div className="font-mono text-[10px] text-ink/50 mt-0.5 uppercase tracking-[0.04em] truncate">
          {item.subtitle}
        </div>
      </div>
      <span className="font-mono text-[10px] text-ink/40 shrink-0">{timeAgo(item.at)}</span>
    </div>
  );
}

export default function RecentActivity() {
  const navigate = useNavigate();
  const activity = useDashboardStore((s) => s.activity);

  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_#0d0d0d]">
      <div className="flex items-center justify-between px-4 py-3 border-b-2 border-ink">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]">
          Recent Activity
        </span>
        <button
          onClick={() => navigate('/portfolio')}
          className="font-mono text-[10.5px] font-bold uppercase tracking-[0.05em] text-orange-500 hover:underline"
        >
          History →
        </button>
      </div>
      {activity.length > 0 ? (
        <div>
          {activity.map((item) => (
            <FeedRow key={item.id} item={item} />
          ))}
        </div>
      ) : (
        <div className="px-4 py-10 text-center font-mono text-[11px] uppercase tracking-[0.08em] text-ink/40">
          No recent activity
        </div>
      )}
    </div>
  );
}
