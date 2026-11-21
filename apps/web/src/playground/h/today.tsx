import { useState } from 'react';

import { ACCOUNT, MARKET, usd } from '../data';

import { Briefs } from './briefs';
import { PerfChart } from './chart';
import { Dateline, Lead, Page } from './frame';
import {
  accountWindow,
  dayLabel,
  drawdown,
  pts,
  pts2,
  RANGES,
  RUNNING,
  tone,
  type Range,
} from './model';
import {
  comingBriefs,
  driftBriefs,
  fillBriefs,
  frontDeck,
  frontHeadline,
  RESTING_STRATEGIES,
  spyVs200,
} from './paper';
import { Story } from './stories';
import { Columns, Kicker, Segmented, Spread } from './ui';

/** The account against SPY as the lead picture, with its figures on one line above. */
export function LeadChart({
  range,
  setRange,
  title = 'Account against SPY',
  height = 260,
}: {
  range: Range;
  setRange: (r: Range) => void;
  title?: string;
  height?: number;
}) {
  const w = accountWindow(range);
  const n = w.main.length;
  const ea = w.main[n - 1];
  const eb = w.bench[n - 1];
  const dd = Math.min(...drawdown(w.main));
  const ddb = Math.min(...drawdown(w.bench));
  return (
    <section>
      <Kicker
        right={
          <Segmented
            label="Range"
            value={range}
            onChange={setRange}
            options={RANGES.map((r) => ({ key: r, label: r }))}
          />
        }
      >
        {title}
      </Kicker>
      <div className="mt-4 flex flex-wrap gap-x-8 gap-y-2 font-mono text-[12px] tabular-nums text-fg-3">
        <span>
          Return <b className={`text-[15px] font-medium ${tone(ea)}`}>{pts(ea)}</b>
        </span>
        <span>
          SPY <b className="text-[15px] font-medium text-fg-2">{pts(eb)}</b>
        </span>
        <span>
          Gap{' '}
          <b className="text-[15px] font-medium text-fg">
            {ea - eb >= 0 ? '+' : '−'}
            {Math.abs(ea - eb).toFixed(1)} pts
          </b>
        </span>
        <span>
          Max drawdown <b className="text-[15px] font-medium text-fg-2">{pts(dd)}</b>{' '}
          <span className="text-fg-3">SPY {pts(ddb)}</span>
        </span>
      </div>
      <div className="mt-5">
        <PerfChart w={w} height={height} />
      </div>
      {w.markers.length > 0 && (
        <ol className="m-0 mt-3 flex list-none flex-wrap gap-x-5 gap-y-1.5 p-0 text-[12px] text-fg-2">
          {w.markers.map((m) => (
            <li key={m.n} className="inline-flex items-center gap-2">
              <i className="grid h-4 w-4 place-items-center rounded-[3px] border border-line-strong font-mono text-[9.5px] not-italic text-fg">
                {m.n}
              </i>
              <span className="font-mono text-[11px] text-fg-3">{dayLabel(w.dates[m.i])}</span>
              {m.label}
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}

export function Today() {
  const [range, setRange] = useState<Range>('3M');
  const spy = MARKET.quotes[0];
  return (
    <Page
      ask={{
        suggestions: [
          'Why is the account down today?',
          "Lower Recession Radar's gold to 30%",
          'Draft a trend strategy on QQQ',
        ],
      }}
    >
      <Lead
        kicker={`Today · ${usd(ACCOUNT.total)} across live and paper`}
        headline={frontHeadline(range)}
        deck={frontDeck()}
      />
      <Spread
        main={
          <>
            <LeadChart range={range} setRange={setRange} />
            <div className="mt-14">
              <Kicker right={`${RUNNING.length} sessions`}>Running</Kicker>
              <Columns cols={3}>
                {RUNNING.map((s) => (
                  <Story key={s.id} s={s} />
                ))}
              </Columns>
            </div>
            <div className="mt-8">
              <Kicker ink={false} right={`${RESTING_STRATEGIES.length} strategies`}>
                Not running
              </Kicker>
              <Columns cols={2}>
                {RESTING_STRATEGIES.map((s) => (
                  <Story key={s.id} s={s} big={false} />
                ))}
              </Columns>
            </div>
          </>
        }
        aside={
          <>
            <Briefs
              title="Market"
              items={[
                {
                  when: 'SPY',
                  title: `${spy.price.toFixed(2)}, ${pts2(spy.change * 100)} today`,
                  detail: `${Math.abs(spyVs200 * 100).toFixed(1)}% ${spyVs200 < 0 ? 'under' : 'over'} its 200-day average`,
                  tone: spy.change < 0 ? 'loss' : 'gain',
                },
                {
                  when: 'QQQ',
                  title: `${MARKET.quotes[1].price.toFixed(2)}, ${pts2(MARKET.quotes[1].change * 100)} today`,
                  detail: 'Nasdaq 100',
                  tone: MARKET.quotes[1].change < 0 ? 'loss' : 'gain',
                },
              ]}
            />
            <Briefs title="Coming up" items={comingBriefs()} />
            <Briefs title="Drift" right="from target" items={driftBriefs()} />
            <Briefs title="Fills" right="this month" items={fillBriefs()} />
          </>
        }
      />
      <Dateline
        items={[
          'Prices Nov 20, 2026, 12:04 ET',
          'paper and live trading on Alpaca',
          'history before Nov 12 is sample data',
        ]}
      />
    </Page>
  );
}
