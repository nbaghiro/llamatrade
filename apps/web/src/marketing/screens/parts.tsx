import type { ReactNode } from 'react';

import { LogoMark } from '../../components/common/Logo';
import type { Shade } from '../data/editorLevels';
import { highlightDsl } from '../lib/dsl';

const NAV = ['Portfolio', 'Strategies', 'Backtests', 'Sessions', 'Copilot'] as const;
export type NavItem = (typeof NAV)[number];

export function AppNav({ on, live = false }: { on: NavItem; live?: boolean }) {
  return (
    <div className="app-nav">
      <span className="lg">
        <LogoMark size={30} bold className="lg-mark" />
        <span className="lg-word">LlamaTrade</span>
      </span>
      <nav>
        {NAV.map((n) => (
          <span key={n} className={n === on ? 'on' : undefined}>
            {n}
          </span>
        ))}
      </nav>
      <div className="end">
        <span>Market open · 10:42 ET</span>
        <span className={live ? 'mode live' : 'mode'}>{live ? 'Live' : 'Paper'}</span>
        <span className="av">SR</span>
      </div>
    </div>
  );
}

export function Panel({
  title,
  aside,
  children,
  className = '',
}: {
  title: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`pn ${className}`}>
      <div className="pn-h">
        <b>{title}</b>
        {aside !== undefined && <span>{aside}</span>}
      </div>
      {children}
    </div>
  );
}

export interface Column {
  label: string;
  numeric?: boolean;
}

export function Table({
  columns,
  children,
  className = '',
}: {
  columns: readonly Column[];
  children: ReactNode;
  className?: string;
}) {
  return (
    <table className={`tbl ${className}`}>
      <thead>
        <tr>
          {columns.map((c) => (
            <th key={c.label} className={c.numeric ? 'n' : undefined}>
              {c.label}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>{children}</tbody>
    </table>
  );
}

export function WeightBar({ parts }: { parts: readonly { shade: Shade; weight: number }[] }) {
  return (
    <div className="wb">
      {parts.map((p, i) => (
        <span key={i} className={p.shade} style={{ width: `calc(${p.weight}% - 2px)` }} />
      ))}
    </div>
  );
}

export type SessionState = 'running' | 'frozen' | 'draft';

const STATE_LABEL: Record<SessionState, string> = {
  running: 'Running',
  frozen: 'Frozen',
  draft: 'Draft',
};

export function Status({ state, label }: { state: SessionState; label?: string }) {
  const cls = state === 'running' ? 'st run' : state === 'frozen' ? 'st frz' : 'st';
  return (
    <span className={cls}>
      <i />
      {label ?? STATE_LABEL[state]}
    </span>
  );
}

export function Side({ side }: { side: 'BUY' | 'SELL' }) {
  return <span className="side">{side}</span>;
}

export function Code({ lines, className = '' }: { lines: readonly string[]; className?: string }) {
  return (
    <div className={`code ${className}`}>
      {lines.map((line, i) => (
        <div key={i}>
          <span className="ln">{i + 1}</span>
          <span>
            {highlightDsl(line).map((t, k) => (
              <span
                key={k}
                className={t.tone === 'keyword' ? 'k' : t.tone === 'string' ? 's' : undefined}
              >
                {t.text}
              </span>
            ))}
          </span>
        </div>
      ))}
    </div>
  );
}

/** A label above a value, used by the figure rows. */
export function Figure({
  label,
  value,
  detail,
  tone,
}: {
  label: string;
  value: ReactNode;
  detail?: ReactNode;
  tone?: 'gain' | 'loss';
}) {
  return (
    <div>
      <span className="lbl">{label}</span>
      <div className={`v ${tone ?? ''}`}>{value}</div>
      {detail !== undefined && <div className={`d ${tone ?? ''}`}>{detail}</div>}
    </div>
  );
}

export function KeyRow({ label, value }: { label: string; value: ReactNode }) {
  return (
    <div className="kv">
      <span className="t2">{label}</span>
      <span className="tnum">{value}</span>
    </div>
  );
}
