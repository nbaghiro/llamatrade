import { useState } from 'react';

import { SESSIONS, signedUsd, strategyById, usd, type Session } from '../data';

import { useAsk } from './askContext';
import { PerfChart } from './chart';
import { FUND_NAME, FUND_TODAY, pts, pts2, sessionActivity, sessionValues, tone } from './model';
import { OutlineView } from './outline';
import { itemsOf } from './outlineModel';
import {
  Button,
  Delta,
  Figure,
  Figures,
  LeftHead,
  LinkButton,
  ListLabel,
  ModeTag,
  PanelFoot,
  PanelHead,
  PickRow,
  Segmented,
  Spark,
  StageCard,
} from './ui';

const SHADES = ['bg-chart-1', 'bg-chart-2', 'bg-chart-3', 'bg-chart-4', 'bg-chart-5'];

function Holdings({ s }: { s: Session }) {
  if (!s.holds.length)
    return <p className="py-6 text-[13px] text-fg-3">Stopped. Positions were closed to cash.</p>;
  return (
    <div>
      <span className="flex h-[6px] w-full overflow-hidden rounded-full bg-sunk">
        {s.holds.map((h, i) => (
          <i
            key={h.symbol}
            className={`block h-full ${SHADES[i % 5]}`}
            style={{ width: `${h.weight}%` }}
          />
        ))}
      </span>
      <div className="mt-3 border-t border-line">
        {s.holds.map((h, i) => {
          const t = FUND_TODAY[h.symbol] ?? 0;
          return (
            <div
              key={h.symbol}
              className="grid grid-cols-[10px_52px_minmax(0,1fr)_56px_96px_64px] items-center gap-3 border-b border-line py-2.5 text-[13px]"
            >
              <i className={`h-2 w-2 rounded-[2px] ${SHADES[i % 5]}`} />
              <span className="font-mono font-medium text-fg">{h.symbol}</span>
              <span className="truncate text-fg-3">{FUND_NAME[h.symbol]}</span>
              <span className="text-right font-mono text-[12px] tabular-nums text-fg-2">
                {h.weight.toFixed(1)}%
              </span>
              <span className="text-right font-mono tabular-nums text-fg">
                {usd((s.value * h.weight) / 100)}
              </span>
              <Delta v={t} className="text-right text-[12px]">
                {pts2(t)}
              </Delta>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Activity({ s }: { s: Session }) {
  return (
    <div className="border-t border-line">
      {sessionActivity(s).map((a, i) => (
        <div
          key={i}
          className="grid grid-cols-[64px_minmax(0,1fr)] gap-3 border-b border-line py-2.5"
        >
          <span className="font-mono text-[12px] text-fg-3">{a.when}</span>
          <span className="min-w-0">
            <span className="block text-[13px] text-fg">{a.what}</span>
            <span className="block truncate text-[12px] text-fg-3">{a.detail}</span>
          </span>
        </div>
      ))}
    </div>
  );
}

type Tab = 'chart' | 'holds' | 'activity' | 'why';

/** One session on the stage. On Today it shows the chart only, with links to go further. */
export function SessionPanel({ s, full = false }: { s: Session; full?: boolean }) {
  const { ask } = useAsk();
  const [tab, setTab] = useState<Tab>('chart');
  const st = strategyById(s.strategyId);
  if (!st) return null;
  const { w, first, since } = sessionValues(s);
  const spySince = w.bench[w.bench.length - 1];
  return (
    <StageCard>
      <PanelHead
        eyebrow={
          <span className="inline-flex items-center gap-2">
            Session <ModeTag mode={s.mode} />
          </span>
        }
        title={st.name}
        meta={`Version ${s.version} · started ${s.started}${s.stoppedOn ? ` · stopped ${s.stoppedOn}` : ''} · ${s.next ?? 'not trading'}`}
        right={
          full ? (
            <Segmented
              label="Show"
              value={tab}
              onChange={setTab}
              options={[
                { key: 'chart', label: 'Chart' },
                { key: 'holds', label: 'Holds' },
                { key: 'activity', label: 'Activity' },
                { key: 'why', label: 'Why' },
              ]}
            />
          ) : undefined
        }
      />
      <div className="mt-[18px]">
        <Figures>
          <Figure label="Value" sub={s.stoppedOn ? 'in cash' : `${signedUsd(s.today)} today`}>
            {usd(s.value).replace(/\.\d+$/, '')}
          </Figure>
          <Figure label="Since start" sub={`SPY ${pts(spySince)}`}>
            <span className={tone(since)}>{pts(since * 100)}</span>
          </Figure>
          <Figure label="Gain" sub={`from ${usd(first).replace(/\.\d+$/, '')}`}>
            {signedUsd(s.value - first).replace(/\.\d+$/, '')}
          </Figure>
        </Figures>
      </div>
      <div className="mt-[18px] min-h-[220px]">
        {tab === 'chart' && (
          <>
            <PerfChart w={w} height={200} mainLabel="Session" drawdownStrip={full} />
            {!full && s.holds.length > 0 && (
              <div className="mt-4 flex items-center gap-3 border-t border-line pt-3">
                <span className="text-[11.5px] text-fg-3">Holds</span>
                <span className="flex h-[5px] flex-1 overflow-hidden rounded-full bg-sunk">
                  {s.holds.map((h, i) => (
                    <i
                      key={h.symbol}
                      className={`block h-full ${SHADES[i % 5]}`}
                      style={{ width: `${h.weight}%` }}
                    />
                  ))}
                </span>
                <span className="font-mono text-[11px] text-fg-2">
                  {s.holds.map((h) => `${h.symbol} ${h.weight.toFixed(0)}%`).join('  ')}
                </span>
              </div>
            )}
          </>
        )}
        {tab === 'holds' && <Holdings s={s} />}
        {tab === 'activity' && <Activity s={s} />}
        {tab === 'why' && (
          <div className="-mx-5 border-y border-line md:-mx-7 md:px-2">
            <OutlineView strategy={st} items={itemsOf(st.name, st.cadence, st.rules)} />
          </div>
        )}
      </div>
      <PanelFoot
        note={
          s.mode === 'live'
            ? 'Trades on your Alpaca live account. Values before Nov 19 are sample data.'
            : 'Trades on your Alpaca paper account. Values before Nov 19 are sample data.'
        }
      >
        {full ? (
          <>
            {!s.stoppedOn && <Button>Pause</Button>}
            {s.stoppedOn ? <Button variant="primary">Restart</Button> : <Button>Stop</Button>}
            <LinkButton to={`/j/strategies/${st.id}`}>Open strategy</LinkButton>
          </>
        ) : (
          <>
            <Button
              variant="quiet"
              onClick={() => ask(`Why does ${st.name} hold this today?`, st.id)}
            >
              Ask why
            </Button>
            <LinkButton to={`/j/sessions/${s.id}`}>Open session</LinkButton>
          </>
        )}
      </PanelFoot>
    </StageCard>
  );
}

export function SessionsLeft({ sel }: { sel: string }) {
  const running = SESSIONS.filter((s) => !s.stoppedOn);
  const total = running.reduce((a, s) => a + s.value, 0);
  const row = (s: Session) => {
    const st = strategyById(s.strategyId);
    const { w, since } = sessionValues(s);
    return (
      <PickRow
        key={s.id}
        to={`/j/sessions/${s.id}`}
        on={sel === s.id}
        muted={Boolean(s.stoppedOn)}
        title={st?.name}
        sub={
          <span className="inline-flex items-center gap-2">
            <ModeTag mode={s.mode} />v{s.version} · since {s.started}
          </span>
        }
        right={
          <>
            <Spark values={w.main} bench={w.bench} width={52} height={20} />
            <Delta v={since} className="w-[54px] text-right text-[12.5px]">
              {pts(since * 100)}
            </Delta>
          </>
        }
      />
    );
  };
  return (
    <>
      <LeftHead
        title="Sessions"
        sub={`${running.length} running with ${usd(total).replace(/\.\d+$/, '')} on Alpaca.`}
      />
      <ListLabel right={<span>Since start</span>}>Running</ListLabel>
      {running.map(row)}
      <ListLabel>Stopped</ListLabel>
      {SESSIONS.filter((s) => s.stoppedOn).map(row)}
    </>
  );
}
