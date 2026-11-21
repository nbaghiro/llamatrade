import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { useWidth } from '../../components/charts/useWidth';
import { pct, signedUsd, usd, type Strategy } from '../data';

import { useAsk } from './askContext';
import {
  activeSession,
  backtestWindow,
  lastBacktest,
  pts,
  sessionValues,
  tone,
  type Window,
} from './model';
import { OutlineView } from './outline';
import { itemsOf } from './outlineModel';
import { stateKicker, statusLine } from './paper';
import { Cell, Head, Mono, Spark, TextLink } from './ui';

/** A sparkline that fills its column. */
export function FluidSpark({
  w,
  height = 44,
  toneBy = true,
}: {
  w: Window;
  height?: number;
  toneBy?: boolean;
}) {
  const [ref, width] = useWidth<HTMLDivElement>(240);
  return (
    <div ref={ref} className="w-full">
      <Spark values={w.main} bench={w.bench} width={width} height={height} toneBy={toneBy} />
    </div>
  );
}

function KickerLine({ s }: { s: Strategy }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="inline-flex items-center gap-1.5">
        {s.state === 'running' && (
          <i
            aria-hidden="true"
            className={`h-1.5 w-1.5 rounded-full ${s.mode === 'live' ? 'bg-gain' : 'border border-fg-3'}`}
          />
        )}
        <Mono className={s.state === 'running' ? 'text-fg' : 'text-fg-3'}>{stateKicker(s)}</Mono>
      </span>
      <span className="text-[11.5px] text-fg-3">{s.cadence}</span>
    </div>
  );
}

function Figure({ s, big }: { s: Strategy; big: boolean }): ReactNode {
  const ses = activeSession(s.id);
  const b = lastBacktest(s.id);
  const size = big ? 'text-[32px]' : 'text-[24px]';
  if (ses) {
    const { since } = sessionValues(ses);
    return (
      <div>
        <span
          className={`font-mono ${size} leading-none tracking-[-0.04em] tabular-nums ${tone(ses.today)}`}
        >
          {signedUsd(ses.today)}
        </span>
        <div className="mt-1.5 font-mono text-[11.5px] tabular-nums text-fg-3">
          {pct(ses.today / (ses.value - ses.today), 2)} today · {usd(ses.value)} ·{' '}
          <span className={tone(since)}>{pts(since * 100)}</span> since {ses.started}
        </div>
      </div>
    );
  }
  if (b)
    return (
      <div>
        <span
          className={`font-mono ${size} leading-none tracking-[-0.04em] tabular-nums ${tone(b.ret)}`}
        >
          {pts(b.ret * 100)}
        </span>
        <div className="mt-1.5 font-mono text-[11.5px] tabular-nums text-fg-3">
          backtest · SPY {pts(b.spy * 100)} · worst {pts(b.worst * 100)}
        </div>
      </div>
    );
  return (
    <div>
      <span className={`font-mono ${size} leading-none tracking-[-0.04em] text-fg-3`}>Not run</span>
      <div className="mt-1.5 font-mono text-[11.5px] text-fg-3">no backtest yet</div>
    </div>
  );
}

function storyWindow(s: Strategy): Window | null {
  const ses = activeSession(s.id);
  if (ses) return sessionValues(ses).w;
  const b = lastBacktest(s.id);
  return b ? backtestWindow(b) : null;
}

/** A front-page story: kicker, name, one big number, a sparkline against SPY, one status line. */
export function Story({ s, big = true }: { s: Strategy; big?: boolean }) {
  const { ask } = useAsk();
  const w = storyWindow(s);
  return (
    <Cell>
      <KickerLine s={s} />
      <Link to={`/h/strategies/${s.id}`} className="mt-3 block hover:underline">
        <Head size={big ? 24 : 19}>{s.name}</Head>
      </Link>
      {big ? (
        <>
          <div className="mt-4">
            <Figure s={s} big />
          </div>
          <div className="mt-4">{w && <FluidSpark w={w} height={46} />}</div>
        </>
      ) : (
        <div className="mt-3 grid grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] items-end gap-5">
          <Figure s={s} big={false} />
          {w ? (
            <FluidSpark w={w} height={30} />
          ) : (
            <div className="h-[30px] border-b border-dashed border-line" />
          )}
        </div>
      )}
      <p className={`m-0 mt-3 leading-[1.45] text-fg-2 ${big ? 'text-[13px]' : 'text-[12.5px]'}`}>
        {statusLine(s)}
      </p>
      <div className={`flex gap-5 ${big ? 'mt-3' : 'mt-2'}`}>
        <TextLink onClick={() => ask(`How is ${s.name} doing?`, s.id)}>Ask about it</TextLink>
        <TextLink to={`/h/strategies/${s.id}`}>Open</TextLink>
      </div>
    </Cell>
  );
}

/** A strategy as a feature: the story's head and figure, then its outline tree. */
export function Feature({ s }: { s: Strategy }) {
  const { ask } = useAsk();
  const w = storyWindow(s);
  const ses = activeSession(s.id);
  return (
    <div className="grid gap-x-10 gap-y-5 border-t border-line pb-9 pt-5 first:border-t-0 md:grid-cols-[250px_minmax(0,1fr)]">
      <div className="min-w-0">
        <KickerLine s={s} />
        <Link to={`/h/strategies/${s.id}`} className="mt-3 block hover:underline">
          <Head size={26}>{s.name}</Head>
        </Link>
        <p className="m-0 mt-2 text-[13px] leading-[1.45] text-fg-2">{s.summary}</p>
        <div className="mt-5">
          <Figure s={s} big={false} />
        </div>
        <div className="mt-3">{w && <FluidSpark w={w} height={30} />}</div>
        <p className="m-0 mt-3 text-[12.5px] leading-[1.45] text-fg-3">{statusLine(s)}</p>
        <div className="mt-3 flex flex-wrap gap-x-5 gap-y-2">
          <TextLink to={`/h/strategies/${s.id}`}>Open builder</TextLink>
          {ses && <TextLink to={`/h/sessions/${ses.id}`}>Session</TextLink>}
          <TextLink onClick={() => ask(`Explain ${s.name}`, s.id)}>Ask about it</TextLink>
        </div>
      </div>
      <div className="min-w-0 self-start overflow-x-auto border-y border-line">
        <OutlineView strategy={s} items={itemsOf(s.name, s.cadence, s.rules)} compact />
      </div>
    </div>
  );
}
