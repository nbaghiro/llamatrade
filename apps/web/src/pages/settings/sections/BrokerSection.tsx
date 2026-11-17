import { toDate } from '@llamatrade/core/format';
import type { AlpacaCredentialsListItem } from '@llamatrade/core/proto/auth_pb';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { AlertTriangle, Check, Minus } from 'lucide-react';
import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { LIVE_REQUIREMENTS } from '../../../components/auth/accountPaths';
import { AlpacaMark } from '../../../components/settings/AlpacaMark';
import { useSessionRows } from '../../../components/shell/useSessionRows';
import { Dialog, ModeBadge, PanelError, Skeleton } from '../../../components/ui';
import { asSentence } from '../../../lib/format';
import { maskedKey as shortKey } from '../../../lib/scope';
import { startAlpacaLink } from '../../../services/alpacaOAuth';
import { useAuthStore } from '../../../store/auth';
import { etTime, problemText, type AccountKind, type AccountProblem } from '../health';
import { keyMismatch, maskedKey, primaryCredential } from '../model';
import { useSettingsSummary } from '../useSettingsSummary';

const CONNECT_PATH = '/connect/alpaca?next=/settings/broker';
const KEYS_PATH = `${CONNECT_PATH}&method=keys`;

const longDay = (d: Date | null) =>
  d
    ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : 'Not available';

function CheckRow({
  state,
  children,
  detail,
}: {
  state: 'pass' | 'fail' | 'unknown';
  children: ReactNode;
  detail?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-2 py-1 text-[12.5px] text-fg">
      {state === 'pass' ? (
        <Check aria-label="Passed" className="h-4 w-4 flex-none text-accent" />
      ) : state === 'fail' ? (
        <AlertTriangle aria-label="Failed" className="h-4 w-4 flex-none text-risk" />
      ) : (
        <Minus aria-label="Not checked" className="h-4 w-4 flex-none text-fg-3" />
      )}
      <span className="min-w-0 flex-1">{children}</span>
      {detail && <span className="num flex-none text-[11.5px] text-fg-3">{detail}</span>}
    </div>
  );
}

function KV({ label, children }: { label: string; children: ReactNode }) {
  return (
    <>
      <dt className="text-fg-3">{label}</dt>
      <dd className="m-0 min-w-0 truncate text-fg">{children}</dd>
    </>
  );
}

function sessionsLine(running: number, stopped: number): string {
  if (running === 0 && stopped === 0) return 'None yet';
  const parts = [];
  if (running) parts.push(`${running} running`);
  if (stopped) parts.push(`${stopped} stopped`);
  return parts.join(' · ');
}

function ProblemStrip({ problem }: { problem: AccountProblem }) {
  const t = problemText(problem);
  const [error, setError] = useState('');
  const [starting, setStarting] = useState(false);
  const approve = () => {
    const token = useAuthStore.getState().accessToken;
    if (!token) return setError('Your session has ended. Please sign in again.');
    setStarting(true);
    startAlpacaLink(token).catch(() => {
      setStarting(false);
      setError("Alpaca sign-in couldn't be started just now. Please try again or paste new keys.");
    });
  };
  const todo =
    problem.reason === 'rejected'
      ? 'The keys were probably regenerated or revoked in Alpaca. Approve LlamaTrade again, or paste the new pair.'
      : 'Approve LlamaTrade on Alpaca again, or paste a new key pair.';
  return (
    <div className="grid gap-3 border-b border-risk-line bg-risk-soft px-4 py-3.5 text-[12.5px] text-fg-2 md:grid-cols-3 md:gap-5">
      <div className="grid content-start gap-1">
        <b className="font-semibold text-fg">What happened</b>
        <span>{t.happened}</span>
      </div>
      <div className="grid content-start gap-1">
        <b className="font-semibold text-fg">What it affects</b>
        <span>{t.affects}</span>
      </div>
      <div className="grid content-start gap-1">
        <b className="font-semibold text-fg">What to do</b>
        <span>{todo}</span>
        <div className="mt-1.5 flex flex-wrap gap-2">
          {problem.kind === 'paper' && (
            <button
              type="button"
              className="btn btn-primary btn-sm"
              onClick={approve}
              disabled={starting}
            >
              <AlpacaMark size={16} />
              {starting ? 'Opening Alpaca…' : 'Approve again'}
            </button>
          )}
          <Link to={KEYS_PATH} className="btn btn-secondary btn-sm">
            Paste new keys
          </Link>
        </div>
        {error && <span className="text-risk">{error}</span>}
      </div>
    </div>
  );
}

interface AccountPanelProps {
  kind: AccountKind;
  cred: AlpacaCredentialsListItem;
  problem: AccountProblem | null;
  running: number;
  stopped: number;
}

function AccountPanel({ kind, cred, problem, running, stopped }: AccountPanelProps) {
  const lastCheck = useBrokerStore((s) => s.lastCheck);
  const remove = useBrokerStore((s) => s.remove);
  const [checkOpen, setCheckOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [removing, setRemoving] = useState(false);
  const check = lastCheck && lastCheck.isPaper === cred.isPaper ? lastCheck : null;
  const label = `Alpaca ${kind}`;

  const status = problem ? (
    <span className="text-[12.5px] font-medium text-risk">{problemText(problem).short}</span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-[12.5px] text-fg-2">
      <i aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-fg" />
      Connected
    </span>
  );

  const disconnect = async () => {
    setRemoving(true);
    await remove(cred.id);
    setRemoving(false);
    setConfirmOpen(false);
  };

  return (
    <section
      aria-label={label}
      className={`min-w-0 overflow-hidden rounded-panel border bg-panel ${
        problem ? 'border-risk-line' : 'border-line'
      }`}
    >
      <header className="flex flex-wrap items-center gap-2.5 border-b border-line px-4 py-3">
        <AlpacaMark />
        <b className="text-[14px] font-semibold">{label}</b>
        <ModeBadge mode={kind} size="sm" />
        <span className="num text-[11.5px] text-fg-3">{shortKey(cred.apiKeyPrefix)}</span>
        <span className="ml-auto">{status}</span>
      </header>
      {problem && <ProblemStrip problem={problem} />}
      <div className="grid gap-4 px-4 py-3.5 md:grid-cols-2 md:gap-8">
        <dl className="m-0 grid grid-cols-[110px_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-[12.5px]">
          <KV label="Key">
            <span className="num">{maskedKey(cred.apiKeyPrefix)}</span>
          </KV>
          <KV label="Name">{cred.name || 'Alpaca account'}</KV>
          <KV label="Connected on">{longDay(toDate(cred.createdAt))}</KV>
          <KV label="Sessions">{sessionsLine(running, stopped)}</KV>
        </dl>
        <div className="grid content-start">
          <CheckRow state={cred.isActive ? 'pass' : 'fail'}>
            {cred.isActive ? 'Keys stored and active' : 'Keys stored but switched off'}
          </CheckRow>
          <CheckRow
            state={check === null ? 'unknown' : check.valid ? 'pass' : 'fail'}
            detail={check ? (check.valid ? etTime(check.at) : `failed ${etTime(check.at)}`) : null}
          >
            Credentials accepted by Alpaca
            {check === null && <span className="text-fg-3"> · not checked from here</span>}
          </CheckRow>
          <CheckRow state="pass">Account is {kind}</CheckRow>
        </div>
      </div>
      {checkOpen && (
        <CheckForm
          prefix={cred.apiKeyPrefix}
          isPaper={cred.isPaper}
          onDone={() => setCheckOpen(false)}
        />
      )}
      <footer className="flex flex-wrap items-center justify-end gap-2 border-t border-line bg-sunk px-4 py-2.5">
        <button
          type="button"
          className="btn btn-secondary btn-sm"
          onClick={() => setCheckOpen((v) => !v)}
          aria-expanded={checkOpen}
        >
          Check the keys
        </button>
        <button type="button" className="btn btn-ghost btn-sm" onClick={() => setConfirmOpen(true)}>
          Disconnect
        </button>
      </footer>
      <Dialog
        open={confirmOpen}
        onClose={() => setConfirmOpen(false)}
        title={`Disconnect ${label}?`}
        footer={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => setConfirmOpen(false)}
            >
              Keep connected
            </button>
            <button
              type="button"
              className="btn btn-danger"
              disabled={removing}
              onClick={() => {
                disconnect().catch(() => setRemoving(false));
              }}
            >
              {removing ? 'Disconnecting…' : 'Disconnect'}
            </button>
          </>
        }
      >
        <p className="m-0 text-[13px] text-fg-2">
          LlamaTrade removes the key {maskedKey(cred.apiKeyPrefix)}. It can&apos;t happen while a
          session or a funded sleeve still uses it, so stop those first. Positions stay in your
          Alpaca account.
        </p>
      </Dialog>
    </section>
  );
}

function NotConnected({ kind }: { kind: AccountKind }) {
  const live = kind === 'live';
  return (
    <section
      aria-label={`Alpaca ${kind}, not connected`}
      className="grid gap-2.5 rounded-panel border border-dashed border-line-strong px-4 py-3.5"
    >
      <div className="flex flex-wrap items-center gap-2.5">
        <AlpacaMark />
        <b className="text-[14px] font-semibold">Alpaca {kind}</b>
        <ModeBadge mode={kind} size="sm" />
        <span className="ml-auto text-[12.5px] text-fg-3">Not connected</span>
      </div>
      <p className="m-0 text-[12.5px] text-fg-2">
        {live
          ? `Real money. Connect it when you want to start a session on live. Paper sessions stay on paper. ${LIVE_REQUIREMENTS}`
          : "Simulated money. Backtests don't need it; connect it when you want to run a paper session."}
      </p>
      <div>
        <Link
          to={live ? `${CONNECT_PATH}&account=live` : CONNECT_PATH}
          className="btn btn-secondary btn-sm"
        >
          Connect {kind}
        </Link>
      </div>
    </section>
  );
}

/** One panel per Alpaca account; a panel with a problem turns amber and explains itself (broker2 A). */
export function BrokerSection() {
  const credentials = useBrokerStore((s) => s.credentials);
  const loaded = useBrokerStore((s) => s.loaded);
  const loading = useBrokerStore((s) => s.loading);
  const error = useBrokerStore((s) => s.error);
  const fetch = useBrokerStore((s) => s.fetch);
  const clearError = useBrokerStore((s) => s.clearError);
  const { health } = useSettingsSummary();
  const rows = useSessionRows();

  useEffect(() => {
    fetch().catch(() => undefined);
  }, [fetch]);

  if (!loaded || (loading && credentials.length === 0)) {
    return (
      <div
        className="grid gap-3 rounded-panel border border-line bg-panel px-4 py-4"
        aria-busy="true"
      >
        <Skeleton className="h-3 w-28" />
        <Skeleton className="h-2.5 w-2/3" />
        <Skeleton className="h-2.5 w-1/2" />
      </div>
    );
  }

  if (error && credentials.length === 0) {
    return (
      <section className="panel">
        <PanelError
          title="Broker details couldn't be loaded"
          cause={asSentence(error)}
          unaffected="Running sessions aren't affected."
          onRetry={() => {
            clearError();
            fetch().catch(() => undefined);
          }}
          retrying={loading}
        />
      </section>
    );
  }

  const byKind = (kind: AccountKind) =>
    primaryCredential(credentials.filter((c) => c.isPaper === (kind === 'paper')));
  const counts = (kind: AccountKind) => {
    const mode = kind === 'live' ? ExecutionMode.LIVE : ExecutionMode.PAPER;
    const mine = rows.filter((r) => r.session.mode === mode);
    return {
      running: mine.filter((r) => r.session.isActive).length,
      stopped: mine.filter((r) => !r.session.isActive).length,
    };
  };
  const shown = (['paper', 'live'] as const).map((kind) => ({ kind, cred: byKind(kind) }));
  const others = credentials.filter((c) => !shown.some((s) => s.cred === c));
  const ordered = [...shown].sort((a, b) => Number(!a.cred) - Number(!b.cred));

  return (
    <div className="grid gap-3">
      {ordered.map(({ kind, cred }) =>
        cred ? (
          <AccountPanel
            key={kind}
            kind={kind}
            cred={cred}
            problem={health.problems.find((p) => p.kind === kind) ?? null}
            {...counts(kind)}
          />
        ) : (
          <NotConnected key={kind} kind={kind} />
        )
      )}

      {others.length > 0 && (
        <section className="panel px-4 py-3 text-[12.5px]">
          <b className="font-semibold">Other stored keys</b>
          {others.map((c) => (
            <div key={c.id} className="num mt-1 text-fg-3">
              {maskedKey(c.apiKeyPrefix)} · {c.isPaper ? 'Paper' : 'Live'}
              {c.isActive ? '' : ' · switched off'}
            </div>
          ))}
        </section>
      )}

      {error && (
        <div
          role="alert"
          className="flex items-center gap-2.5 rounded-[8px] border border-risk-line bg-risk-soft px-3 py-2.5 text-[12.5px] text-fg-2"
        >
          <AlertTriangle className="h-4 w-4 flex-none text-risk" />
          <span className="min-w-0 flex-1">{error}</span>
          <button type="button" className="btn btn-ghost btn-sm" onClick={clearError}>
            Dismiss
          </button>
        </div>
      )}

      <p className="m-0 text-[12px] text-fg-3">
        LlamaTrade stores keys encrypted and never shows the secret again. Disconnecting an account
        needs its sessions stopped first. Positions stay in your Alpaca account.
      </p>
    </div>
  );
}

interface CheckFormProps {
  prefix: string;
  isPaper: boolean;
  onDone: () => void;
}

function CheckForm({ prefix, isPaper, onDone }: CheckFormProps) {
  const check = useBrokerStore((s) => s.check);
  const checking = useBrokerStore((s) => s.checking);
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [problem, setProblem] = useState<string | null>(null);

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    const mismatch = keyMismatch(apiKey, prefix);
    if (mismatch) return setProblem(mismatch);
    if (!apiSecret.trim()) return setProblem('Enter the secret key.');
    setProblem(null);
    const result = await check({ apiKey: apiKey.trim(), apiSecret: apiSecret.trim(), isPaper });
    if (result) {
      setApiKey('');
      setApiSecret('');
      onDone();
    }
  };

  return (
    <form
      onSubmit={(e) => {
        submit(e).catch(() => undefined);
      }}
      className="grid gap-2.5 border-t border-line bg-sunk px-4 py-3"
    >
      <p className="m-0 text-xs text-fg-2">
        LlamaTrade never sends the stored secret back to your browser, so paste the key pair to
        check it with Alpaca. Nothing is saved.
      </p>
      <div className="grid gap-2 sm:grid-cols-2">
        <input
          className="input num"
          aria-label="API key ID"
          placeholder={`${prefix}…`}
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          autoComplete="off"
          spellCheck={false}
        />
        <input
          className="input num"
          type="password"
          aria-label="Secret key"
          placeholder="Secret key"
          value={apiSecret}
          onChange={(e) => setApiSecret(e.target.value)}
          autoComplete="off"
        />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <span className="text-xs text-risk">{problem}</span>
        <button type="submit" className="btn btn-primary btn-sm" disabled={checking}>
          {checking ? 'Checking…' : 'Run check'}
        </button>
      </div>
    </form>
  );
}
