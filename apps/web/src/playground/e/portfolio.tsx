import { useMemo, useState } from 'react';

import { ACCOUNT, usd } from '../data';

import { Page, PageHead } from './frame';
import { CASH_TOTAL, CLASSES, HOLDS, PORTFOLIO_COLS, portfolioRows } from './rows';
import { ACCOUNT_SCOPE, type Scope } from './scope';
import { ScopeSheet } from './sheet';
import { LedgerTree } from './tree';
import { Foot } from './ui';

const BASE: Scope = { ...ACCOUNT_SCOPE, path: ['Portfolio'] };
const shade = (i: number) => `rgb(var(--fg) / ${Math.max(0.14, 0.9 - i * 0.13).toFixed(2)})`;

/** Asset classes as one stacked bar; hovering a part names it. */
function ClassBar({ hot, onHot }: { hot: string | null; onHot: (n: string | null) => void }) {
  const parts = [
    ...CLASSES.map((c) => ({ name: c.name, value: c.value })),
    { name: 'Cash', value: CASH_TOTAL },
  ];
  return (
    <div className="px-4 pb-4 md:px-6">
      <div className="flex h-2.5 w-full overflow-hidden rounded-full bg-sunk">
        {parts.map((p, i) => (
          <span
            key={p.name}
            title={`${p.name} ${((p.value / ACCOUNT.total) * 100).toFixed(1)}%`}
            onMouseEnter={() => onHot(p.name)}
            onMouseLeave={() => onHot(null)}
            className={`block h-full border-r border-canvas transition-opacity last:border-r-0 ${hot && hot !== p.name ? 'opacity-30' : ''}`}
            style={{
              width: `${(p.value / ACCOUNT.total) * 100}%`,
              background:
                p.name === 'Cash'
                  ? 'repeating-linear-gradient(135deg, rgb(var(--fg-3)) 0 1px, transparent 1px 4px)'
                  : shade(i),
            }}
          />
        ))}
      </div>
      <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[11.5px] text-fg-3">
        {parts.map((p, i) => (
          <span
            key={p.name}
            className={`inline-flex items-center gap-1.5 ${hot === p.name ? 'text-fg' : ''}`}
          >
            <i
              className={`h-2 w-2 rounded-[2px] ${p.name === 'Cash' ? 'border border-fg-3' : ''}`}
              style={p.name === 'Cash' ? undefined : { background: shade(i) }}
            />
            {p.name}
            <span className="font-mono tabular-nums">
              {((p.value / ACCOUNT.total) * 100).toFixed(1)}%
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

export function Portfolio() {
  const rows = useMemo(() => portfolioRows(), []);
  const [scope, setScope] = useState<Scope>(BASE);
  const [hot, setHot] = useState<string | null>(null);
  return (
    <Page ask={false} art="own">
      <PageHead
        eyebrow="Nov 20, 2026 · 12:04 ET"
        title="Portfolio"
        meta={`${usd(ACCOUNT.total)} across live and paper · ${HOLDS.length} funds in ${CLASSES.length} asset classes`}
      />
      <ScopeSheet scope={scope}>
        <div className="pt-4">
          <ClassBar hot={hot} onHot={setHot} />
        </div>
        <div className="border-t border-line">
          <LedgerTree
            label="Holdings by asset class"
            name="Asset class, fund and the sessions that hold it"
            rows={rows}
            cols={PORTFOLIO_COLS}
            selected={scope.key}
            onSelect={(r) => setScope(r.scope ?? BASE)}
          />
        </div>
      </ScopeSheet>
      <Foot
        items={[
          'Prices Nov 20, 2026, 12:04 ET',
          'ink marks money held on live',
          'fund returns and history are sample data',
        ]}
      />
    </Page>
  );
}
