import { useState } from 'react';

import EquityView from './EquityView';
import MarketsView from './MarketsView';

type Tab = 'portfolio' | 'markets';
const TABS: { key: Tab; label: string }[] = [
  { key: 'portfolio', label: 'Portfolio' },
  { key: 'markets', label: 'Markets' },
];

/** Centered dashboard hero: portfolio equity curve or a single-symbol price chart. */
export default function ChartHero() {
  const [tab, setTab] = useState<Tab>('portfolio');

  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_rgb(var(--lt-ink))] flex flex-col">
      <div className="flex justify-end px-[18px] pt-3 pb-1">
        <div className="flex">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={`font-mono text-[10px] font-bold uppercase tracking-[0.08em] border-[1.5px] border-ink px-2.5 py-1 -ml-[1.5px] first:ml-0 transition-colors ${
                tab === t.key ? 'bg-ink text-bone' : 'bg-paper text-ink hover:bg-ink/5'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === 'portfolio' ? <EquityView /> : <MarketsView />}
    </div>
  );
}
