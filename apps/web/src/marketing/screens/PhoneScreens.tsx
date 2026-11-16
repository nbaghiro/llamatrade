import type { ReactNode } from 'react';

import { SLEEVE_SPLIT } from '../data/illustrative';

import { Status, WeightBar } from './parts';
import { AccountChart } from './PortfolioScreen';

const TABS = ['Home', 'Portfolio', 'Strategies', 'Copilot', 'Account'] as const;

function PhoneShell({
  tab,
  children,
  footer,
}: {
  tab: (typeof TABS)[number];
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <>
      <div className="sb">
        <span>9:41</span>
        <i />
      </div>
      <div className="body">{children}</div>
      {footer}
      <div className="mtabs">
        {TABS.map((t) => (
          <span key={t} className={t === tab ? 'on' : undefined}>
            <i />
            {t}
          </span>
        ))}
      </div>
    </>
  );
}

function Row({
  label,
  value,
  labelClass,
  valueClass,
}: {
  label: ReactNode;
  value: ReactNode;
  labelClass?: string;
  valueClass?: string;
}) {
  return (
    <div className="row">
      <span className={labelClass}>{label}</span>
      <span className={valueClass}>{value}</span>
    </div>
  );
}

export function HomePhone() {
  return (
    <PhoneShell tab="Home">
      <span className="lbl">Today · Paper</span>
      <div className="big">$103,410.27</div>
      <div className="gain today">+$895.40 (+0.87%)</div>
      <div className="mcard chart-card">
        <AccountChart height={150} compact />
      </div>
      <div className="mcard rows">
        <Row label="All-Weather" value="−$84.12" valueClass="tnum loss" />
        <Row label="Recession Radar" value="+$112.40" valueClass="tnum gain" />
        <Row label="Tech Momentum" value="+$867.12" valueClass="tnum gain" />
      </div>
      <div className="mcard rows">
        <Row label="Next rebalance" value="Dec 1" labelClass="t2" valueClass="tnum" />
        <Row label="Reconciliation" value="Passed 10:15" labelClass="t2" />
        <Row label="Frozen sleeves" value={<Status state="frozen" label="1" />} labelClass="t2" />
      </div>
    </PhoneShell>
  );
}

export function PortfolioPhone() {
  const sleeves: [string, string, ReactNode][] = [
    ['All-Weather Portfolio', '$35,982.55', <Status key="a" state="running" />],
    ['Recession Radar', '$25,436.18', <Status key="b" state="frozen" />],
    ['Tech Momentum', '$24,914.42', <Status key="c" state="running" />],
    ['Unallocated', '$17,077.12', null],
  ];
  return (
    <PhoneShell
      tab="Portfolio"
      footer={
        <div className="body body-foot">
          <div className="mcard rows">
            <Row label="Today" value="+$895.40" labelClass="t2" valueClass="tnum gain" />
            <Row label="Paper account" value="Alpaca · 9cc" labelClass="t2" />
          </div>
        </div>
      }
    >
      <h4>Portfolio</h4>
      <div className="mcard">
        <span className="lbl">Total equity</span>
        <div className="big mid">$103,410.27</div>
        <WeightBar parts={SLEEVE_SPLIT} />
      </div>
      <div className="mcard rows">
        {sleeves.map(([name, value, state]) => (
          <div key={name} className="row top">
            <span>
              {name}
              {state && <br />}
              {state}
            </span>
            <span className="tnum">{value}</span>
          </div>
        ))}
      </div>
    </PhoneShell>
  );
}

export function CopilotPhone() {
  return (
    <PhoneShell tab="Copilot">
      <h4>Copilot</h4>
      <div className="msg me wide">
        <div className="bub">Hold bonds when SPY looks stretched.</div>
      </div>
      <div className="msg ai wider">
        <div className="bub">
          When RSI(SPY, 14) is above 70, hold TLT and GLD at 60 and 40. Otherwise hold the two
          strongest of VTI, QQQ and IWM.
        </div>
      </div>
      <div className="mcard">
        <div className="flex items-center justify-between">
          <b>Recession Radar</b>
          <span className="chip ok">Valid</span>
        </div>
        <div className="my-3">
          <WeightBar
            parts={[
              { shade: 'hacc', weight: 54.3 },
              { shade: 'h2', weight: 45.7 },
            ]}
          />
        </div>
        <span className="t3 small">Would hold QQQ and VTI today</span>
      </div>
      <div className="mb">Approve and backtest</div>
      <div className="mb s">Decline</div>
    </PhoneShell>
  );
}

export function StrategyPhone() {
  return (
    <PhoneShell tab="Strategies">
      <span className="lbl">Strategy · Live</span>
      <h4>Tech Momentum Rotation</h4>
      <Status state="running" label="Running since Oct 1" />
      <div className="mcard">
        <span className="lbl">Sleeve equity</span>
        <div className="big mid">$24,914.42</div>
        <div className="gain font-medium">+$867.12 today</div>
      </div>
      <div className="mcard">
        <span className="lbl">Holdings and targets</span>
        {(
          [
            ['QQQ', 49.7],
            ['SMH', 48.8],
          ] as const
        ).map(([sym, w]) => (
          <div key={sym} className="target">
            <b className="sym">{sym}</b>
            <div className="track">
              <span className="h2" style={{ width: `${w}%` }} />
              <span className="mark" />
            </div>
            <span className="tnum text-right">{w}%</span>
          </div>
        ))}
      </div>
      <div className="mcard rows">
        <Row label="Next rebalance" value="Dec 1" labelClass="t2" valueClass="tnum" />
        <Row label="Reconciliation" value="Passed 10:15" labelClass="t2" />
      </div>
    </PhoneShell>
  );
}
