import { Plus } from 'lucide-react';
import { useState, type KeyboardEvent } from 'react';

import {
  ExampleBacktestPanel,
  ExampleBacktestStrip,
} from '../components/auth/ExampleBacktestPanel';
import { InviteForm } from '../marketing/components/InviteForm';
import { EDITOR_LEVELS } from '../marketing/data/editorLevels';

import { ArtBackdrop, Card, Kicker, SectionHead, WRAP } from './ui';

const SECTION = 'py-20 md:py-28';

const HOW: readonly [string, string][] = [
  [
    'Describe or build a strategy',
    'Write it in plain English, arrange blocks, or edit the code. All three change the same strategy.',
  ],
  [
    'Backtest it against SPY',
    'The backtest runs on the engine that runs live sessions, and every figure sits beside the benchmark.',
  ],
  ['Run it on your Alpaca account', 'Start in paper, then run it live on your own Alpaca account.'],
];

export function How() {
  return (
    <section id="how" className={`${WRAP} pb-20 pt-8 md:pb-28 md:pt-12`}>
      <SectionHead kicker="How it works" title="Three steps from an idea to a running strategy." />
      <ol className="m-0 mt-12 grid list-none grid-cols-1 gap-px overflow-hidden rounded-[14px] border border-line bg-line p-0 md:grid-cols-3">
        {HOW.map(([h, p], i) => (
          <li key={h} className="grid content-start gap-3 bg-canvas p-6 md:p-8">
            <span className="font-mono text-[12px] tabular-nums text-fg-3">0{i + 1}</span>
            <h3 className="m-0 text-[19px] font-semibold tracking-[-0.015em]">{h}</h3>
            <p className="m-0 text-[14.5px] leading-relaxed text-fg-2">{p}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}

/** Each Build example as one plain sentence, in the order of EDITOR_LEVELS. */
const SENTENCES = [
  'Hold VTI, VXUS, BND and GLD in equal parts, and rebalance every quarter.',
  'Each month, hold the two of QQQ, XLK and SMH with the best 90-day return, in equal parts.',
  'When the 14-day RSI of SPY is above 70, hold TLT 60% and GLD 40%. Otherwise hold the two of VTI, QQQ and IWM with the strongest 90-day momentum.',
];

const PIECES: readonly [string, string][] = [
  [
    'Weights',
    'Set them yourself, split equally, or weight by momentum, inverse volatility, minimum variance or risk parity.',
  ],
  ['Filters', 'Rank funds by a measure such as momentum and keep the top few.'],
  ['Conditions', 'If and else branches on indicators such as RSI, moving averages and MACD.'],
  ['Schedule', 'Rebalance daily, weekly, monthly, quarterly or annually.'],
];

export function Build() {
  const [level, setLevel] = useState(EDITOR_LEVELS.length - 1);
  const cur = EDITOR_LEVELS[level];

  const onKey = (e: KeyboardEvent<HTMLDivElement>) => {
    const step = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (level + step + EDITOR_LEVELS.length) % EDITOR_LEVELS.length;
    setLevel(next);
    document.getElementById(`sn-lvl-${EDITOR_LEVELS[next].id}`)?.focus();
  };

  return (
    <section id="build" className="border-y border-line bg-panel">
      <div
        className={`${WRAP} ${SECTION} grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)] lg:gap-16`}
      >
        <div className="grid content-start gap-10">
          <SectionHead
            kicker="What you can build"
            title="One language, three editors."
            lede="Blocks, code and the copilot edit the same strategy, so you can start in one and finish in another."
          />
          <dl className="m-0 grid gap-0 border-t border-line">
            {PIECES.map(([h, p]) => (
              <div
                key={h}
                className="grid gap-1 border-b border-line py-4 sm:grid-cols-[120px_minmax(0,1fr)] sm:gap-6"
              >
                <dt className="font-mono text-[11.5px] uppercase tracking-[0.12em] text-fg-3 sm:pt-0.5">
                  {h}
                </dt>
                <dd className="m-0 text-[14.5px] leading-relaxed text-fg-2">{p}</dd>
              </div>
            ))}
          </dl>
        </div>
        <div className="grid content-start gap-4">
          <div
            role="tablist"
            aria-label="Example strategy"
            onKeyDown={onKey}
            className="flex gap-1 self-start"
          >
            {EDITOR_LEVELS.map((l, i) => (
              <button
                key={l.id}
                id={`sn-lvl-${l.id}`}
                type="button"
                role="tab"
                aria-selected={i === level}
                aria-controls="sn-lvl-panel"
                tabIndex={i === level ? 0 : -1}
                onClick={() => setLevel(i)}
                className={`rounded-full px-3.5 py-1.5 text-[13px] transition-colors ${
                  i === level ? 'bg-sunk font-medium text-fg' : 'text-fg-3 hover:text-fg'
                }`}
              >
                {l.tab}
              </button>
            ))}
          </div>
          <Card plain className="p-0">
            <div id="sn-lvl-panel" role="tabpanel" aria-label={cur.name}>
              <div className="grid gap-1 border-b border-line px-6 py-5">
                <h3 className="m-0 text-[18px] font-semibold tracking-[-0.015em]">{cur.name}</h3>
                <span className="text-[12px] text-fg-3">{cur.meta}</span>
              </div>
              <div className="grid gap-2 border-b border-line px-6 py-5">
                <span className="text-[11px] font-medium text-fg-3">In plain English</span>
                <p className="m-0 text-[15.5px] leading-relaxed">{SENTENCES[level]}</p>
              </div>
              <div className="grid gap-2 px-6 py-5">
                <span className="text-[11px] font-medium text-fg-3">As code</span>
                <pre className="m-0 overflow-x-auto font-mono text-[12.5px] leading-[1.7] text-fg-2">
                  {cur.code.join('\n')}
                </pre>
              </div>
              <div className="flex flex-wrap gap-x-6 gap-y-1 border-t border-line px-6 py-3.5 font-mono text-[11.5px] text-fg-3">
                {cur.needs.map(([k, v]) => (
                  <span key={k}>
                    {k} <span className="text-fg-2">{v}</span>
                  </span>
                ))}
              </div>
            </div>
          </Card>
        </div>
      </div>
    </section>
  );
}

const BACKTEST_NOTES: readonly [string, string][] = [
  ['Same engine', 'A backtest uses the code that runs a live session, so the decisions match.'],
  ['Against SPY', 'Every figure sits beside the benchmark.'],
  ['Drawdown', 'The worst stretch, on its own scale.'],
  ['Run log', 'Progress streams as it runs. Cancel any time.'],
];

export function Backtest() {
  return (
    <section id="backtest" className="sn-art-fade sn-art-fade-top relative overflow-hidden">
      <ArtBackdrop className="sn-art-side" />
      <div
        className={`${WRAP} ${SECTION} relative grid grid-cols-1 items-center gap-12 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:gap-16`}
      >
        <div className="grid content-start gap-10">
          <SectionHead
            kicker="Backtest"
            title="Backtest on the live engine."
            lede="A backtest replays history with the same engine that runs paper and live sessions."
          />
          <ul className="m-0 grid list-none gap-5 p-0">
            {BACKTEST_NOTES.map(([h, p]) => (
              <li key={h} className="grid gap-1 border-l border-line-strong pl-4">
                <b className="text-[14.5px] font-medium">{h}</b>
                <span className="text-[14px] leading-relaxed text-fg-2">{p}</span>
              </li>
            ))}
          </ul>
          <p className="m-0 max-w-[460px] text-[12.5px] leading-relaxed text-fg-3">
            Market data comes from Alpaca&apos;s IEX feed, about 3% of US volume. Past results
            don&apos;t predict future returns.
          </p>
        </div>
        <Card className="hidden min-w-0 justify-self-center p-5 sm:block md:p-7 lg:justify-self-end">
          <ExampleBacktestPanel />
        </Card>
        <Card className="p-2 sm:hidden">
          <ExampleBacktestStrip />
        </Card>
      </div>
    </section>
  );
}

const COPILOT_STEPS = [
  'Describe the funds and the rule.',
  'Get a validated draft.',
  'Edit it as blocks or code.',
  'Backtest, then run it in paper or live.',
];

function Fund({ sym }: { sym: string }) {
  return (
    <span className="mx-0.5 rounded-[4px] border border-line bg-sunk px-1.5 py-px font-mono text-[11.5px]">
      {sym}
    </span>
  );
}

export function Copilot() {
  return (
    <section id="copilot" className="border-y border-line bg-panel">
      <div
        className={`${WRAP} ${SECTION} grid grid-cols-1 items-center gap-12 lg:grid-cols-2 lg:gap-16`}
      >
        <div className="grid content-start gap-8">
          <SectionHead
            kicker="Copilot"
            title="Describe a strategy in plain English."
            lede="The copilot writes validated rules. Nothing runs until you accept."
          />
          <ol className="m-0 grid list-none gap-3 p-0">
            {COPILOT_STEPS.map((s, i) => (
              <li key={s} className="flex items-baseline gap-3 text-[15px] text-fg-2">
                <span className="font-mono text-[11.5px] tabular-nums text-fg-3">0{i + 1}</span>
                {s}
              </li>
            ))}
          </ol>
        </div>
        <Card plain className="grid gap-5 p-5 md:p-7">
          <p className="m-0 max-w-[440px] justify-self-end rounded-[12px] border border-line bg-sunk px-4 py-3 text-[14px] leading-relaxed">
            Hold the strongest of VTI, QQQ and IWM, and move to TLT and GLD when SPY looks
            overbought. Check monthly.
          </p>
          <div className="grid gap-3 rounded-[10px] border border-line p-4 md:p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <span className="text-[15px] font-semibold">Index Rotation</span>
              <span className="text-[12px] text-fg-3">Monthly · 5 funds · vs SPY</span>
            </div>
            <ol className="m-0 grid list-none gap-2.5 p-0 text-[13.5px] leading-[1.9] text-fg-2">
              <li className="flex gap-3">
                <span className="font-mono text-[11px] text-fg-3">1</span>
                <span>
                  When the 14-day RSI of <Fund sym="SPY" /> is above 70, hold <Fund sym="TLT" /> and{' '}
                  <Fund sym="GLD" />, half each.
                </span>
              </li>
              <li className="flex gap-3">
                <span className="font-mono text-[11px] text-fg-3">2</span>
                <span>
                  Otherwise hold the one of <Fund sym="VTI" />
                  <Fund sym="QQQ" />
                  <Fund sym="IWM" /> with the best 90-day return.
                </span>
              </li>
            </ol>
          </div>
          <span className="text-[12px] text-fg-3">
            Copilot drafts it. Nothing trades until you start a session.
          </span>
        </Card>
      </div>
    </section>
  );
}

const PATH: readonly [string, string][] = [
  ['Connect Alpaca', 'Link your Alpaca account. Keys are encrypted at rest.'],
  ['Paper session', 'Run the strategy on your Alpaca paper account first.'],
  ['Live session', 'Move it to your live Alpaca account when you’re ready.'],
];

const GUARDS: readonly [string, string][] = [
  ['Seven risk checks', 'A failed check stops the order and says why.'],
  ['Sells first', 'Sales fund the buys.'],
  ['Reconciliation', 'A mismatch with Alpaca freezes the sleeve.'],
  ['On your phone', 'A stopped order or a frozen session reaches your lock screen.'],
];

export function Live() {
  return (
    <section id="live" className={`${WRAP} ${SECTION}`}>
      <SectionHead
        kicker="Paper, then live"
        title="What you backtest is what trades."
        lede="Paper and live sessions use the same evaluation, sizing and dates as the backtest."
      />
      <ol className="m-0 mt-12 grid list-none grid-cols-1 gap-4 p-0 md:grid-cols-3">
        {PATH.map(([h, p], i) => (
          <li
            key={h}
            className="relative grid content-start gap-2 rounded-[14px] border border-line p-6"
          >
            <span className="flex items-center gap-3 font-mono text-[11.5px] uppercase tracking-[0.12em] text-fg-3">
              <span
                aria-hidden="true"
                className={`h-2 w-2 rounded-full ${i === 2 ? 'bg-gain' : 'border border-fg-3'}`}
              />
              Step {i + 1}
            </span>
            <h3 className="m-0 mt-2 text-[18px] font-semibold tracking-[-0.015em]">{h}</h3>
            <p className="m-0 text-[14px] leading-relaxed text-fg-2">{p}</p>
          </li>
        ))}
      </ol>
      <div className="mt-4 grid grid-cols-1 border-y border-line sm:grid-cols-2 lg:grid-cols-4">
        {GUARDS.map(([h, p], i) => (
          <div
            key={h}
            className={`grid content-start gap-1.5 py-5 sm:px-5 ${
              i > 0 ? 'border-t border-line sm:border-t-0' : ''
            } ${i % 2 ? 'sm:border-l sm:border-line' : ''} ${
              i >= 2 ? 'sm:border-t lg:border-t-0' : ''
            } ${i === 2 ? 'lg:border-l lg:border-line' : ''} ${i === 0 || i === 2 ? 'sm:pl-0' : ''} ${
              i === 2 ? 'lg:pl-5' : ''
            }`}
          >
            <b className="text-[14.5px] font-medium">{h}</b>
            <span className="text-[13.5px] leading-relaxed text-fg-2">{p}</span>
          </div>
        ))}
      </div>
    </section>
  );
}

const OWN: readonly [string, string][] = [
  ['Alpaca holds your funds', 'LlamaTrade places orders and never holds money.'],
  ['Encrypted keys', 'Encrypted at rest, scoped per session.'],
  ['Books that balance', 'A ledger sleeve per strategy, reconciled with Alpaca.'],
  ['Paper or live', 'Start in paper, then go live on your Alpaca account.'],
];

const LOOP = ['Build', 'Backtest', 'Deploy', 'Monitor'];

export function Own() {
  return (
    <section id="own" className="border-y border-line bg-panel">
      <div className={`${WRAP} ${SECTION}`}>
        <SectionHead
          kicker="Your account"
          title="Your keys. Your account."
          lede="LlamaTrade automates an account you own."
        />
        <div className="mt-12 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {OWN.map(([h, p]) => (
            <div
              key={h}
              className="grid content-start gap-2 rounded-[14px] border border-line bg-canvas p-6"
            >
              <h3 className="m-0 text-[16px] font-semibold tracking-[-0.01em]">{h}</h3>
              <p className="m-0 text-[14px] leading-relaxed text-fg-2">{p}</p>
            </div>
          ))}
        </div>
        <div className="mt-8 flex flex-wrap items-center gap-x-3 gap-y-2 font-mono text-[12px] text-fg-3">
          {LOOP.map((s, i) => (
            <span key={s} className="flex items-center gap-3">
              <span className="text-fg-2">{s}</span>
              <span aria-hidden="true">{i < LOOP.length - 1 ? '→' : '↺'}</span>
            </span>
          ))}
          <span>edit, version, redeploy</span>
        </div>
      </div>
    </section>
  );
}

const INCLUDED = [
  'Blocks, code and the copilot',
  'Backtests on the live engine',
  'Paper and live sessions on your Alpaca account',
];

export function Join() {
  return (
    <section id="join" className="sn-art-fade-top relative overflow-hidden">
      <ArtBackdrop />
      <div className={`${WRAP} relative grid grid-cols-1 place-items-center py-24 md:py-32`}>
        <Card className="grid w-full max-w-[560px] grid-cols-1 justify-items-center gap-5 px-5 py-9 text-center md:px-10 md:py-11">
          <Kicker>Invite only</Kicker>
          <div className="grid gap-1">
            <span className="font-mono text-[44px] font-medium leading-none tracking-[-0.03em]">
              $0
            </span>
            <span className="text-[13.5px] text-fg-3">while sign-up is by invite</span>
          </div>
          <ul className="m-0 grid list-none gap-2 p-0 text-[14.5px] text-fg-2">
            {INCLUDED.map((s) => (
              <li key={s}>{s}</li>
            ))}
          </ul>
          <div className="mt-2 w-full">
            <InviteForm id="join-invite" source="join" />
          </div>
          <span className="-mt-3 text-[12.5px] text-fg-3">Places open in small groups.</span>
        </Card>
      </div>
    </section>
  );
}

const FAQ: readonly [string, string][] = [
  [
    'Who holds my money?',
    'Alpaca is the broker and holds the funds. LlamaTrade places orders on your Alpaca account and never holds money.',
  ],
  [
    'Do I need to write code?',
    'No. You can build a strategy from blocks or describe it to the copilot. The code is there if you want to read or edit it.',
  ],
  [
    'How often does a strategy trade?',
    'It rebalances on the schedule you set: daily, weekly, monthly, quarterly or annually.',
  ],
  [
    'How close is a backtest to a live session?',
    'Both run on the same engine, with the same evaluation, sizing and dates. Market data comes from Alpaca’s IEX feed, about 3% of US volume, and past results don’t predict future returns.',
  ],
  [
    'Can I try it without real money?',
    'Yes. Every strategy can run as a paper session first. Live sessions trade real money in your Alpaca account.',
  ],
  ['What does it cost?', 'Nothing while sign-up is by invite.'],
  [
    'How do I get access?',
    'Request an invite with your email. Places open in small groups, and we’ll email you when one opens.',
  ],
];

export function Faq() {
  return (
    <section id="faq" className={`${WRAP} ${SECTION}`}>
      <div className="grid grid-cols-1 gap-12 lg:grid-cols-[minmax(0,0.8fr)_minmax(0,1.2fr)] lg:gap-16">
        <SectionHead kicker="FAQ" title="Questions" />
        <div className="border-t border-line">
          {FAQ.map(([q, a]) => (
            <details key={q} className="group border-b border-line">
              <summary className="flex cursor-pointer items-center justify-between gap-6 py-5 text-[16px] font-medium">
                {q}
                <Plus
                  size={16}
                  strokeWidth={1.75}
                  aria-hidden="true"
                  className="sn-plus flex-none text-fg-3 transition-transform"
                />
              </summary>
              <p className="m-0 max-w-[620px] pb-5 text-[14.5px] leading-relaxed text-fg-2">{a}</p>
            </details>
          ))}
        </div>
      </div>
    </section>
  );
}
