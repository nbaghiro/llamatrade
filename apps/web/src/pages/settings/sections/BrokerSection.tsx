import { toDate } from '@llamatrade/core/format';
import type { AlpacaCredentialsListItem } from '@llamatrade/core/proto/auth_pb';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { AlertTriangle } from 'lucide-react';
import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { LIVE_REQUIREMENTS } from '../../../components/auth/accountPaths';
import { AlpacaMark } from '../../../components/settings/AlpacaMark';
import { useSessionRows } from '../../../components/shell/useSessionRows';
import { Dialog, ModeBadge, PanelError, Segmented, Skeleton } from '../../../components/ui';
import { asSentence } from '../../../lib/format';
import { maskedAccount } from '../../../lib/scope';
import { startAlpacaLink } from '../../../services/alpacaOAuth';
import { useAuthStore } from '../../../store/auth';
import {
  brokerEvents,
  filterEvents,
  readChecks,
  recordCheck,
  type BrokerEvent,
  type BrowserCheck,
  type LogFilter,
} from '../brokerLog';
import { etTime, problemText, type AccountKind, type AccountProblem } from '../health';
import { keyMismatch, maskedKey, primaryCredential } from '../model';
import { useSettingsSummary } from '../useSettingsSummary';

const CONNECT_PATH = '/connect/alpaca?next=/settings/broker';
const KEYS_PATH = `${CONNECT_PATH}&method=keys`;

const longDay = (d: Date | null) =>
  d
    ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : 'Not available';

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
    <div className="grid gap-3 border-b border-risk-line bg-risk-soft px-4 py-3.5 text-[12.5px] text-fg-2">
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
  onChecked: (check: BrowserCheck) => void;
}

/** One compact account tile: who it is, the key, since when, its sessions and the last check. */
function AccountPanel({ kind, cred, problem, running, stopped, onChecked }: AccountPanelProps) {
  const lastCheck = useBrokerStore((s) => s.lastCheck);
  const [checkOpen, setCheckOpen] = useState(false);
  const check = lastCheck && lastCheck.isPaper === cred.isPaper ? lastCheck : null;
  const label = kind === 'paper' ? 'Paper' : 'Live';

  const status = problem ? (
    <span className="text-[12.5px] font-medium text-risk">{problemText(problem).short}</span>
  ) : (
    <span className="inline-flex items-center gap-1.5 text-[12.5px] text-fg-2">
      <i aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-fg" />
      Connected
    </span>
  );

  return (
    <section
      aria-label={`Alpaca ${kind}`}
      className={`min-w-0 overflow-hidden rounded-panel border bg-panel ${
        problem ? 'border-risk-line' : 'border-line'
      }`}
    >
      <header className="flex flex-wrap items-center gap-2.5 px-4 pt-3">
        <AlpacaMark />
        <b className="text-[14px] font-semibold">{label}</b>
        <span className="num text-[11.5px] text-fg-3">{maskedAccount(cred.accountNumber)}</span>
        <span className="ml-auto">{status}</span>
      </header>
      {problem && (
        <div className="mt-3">
          <ProblemStrip problem={problem} />
        </div>
      )}
      <dl className="m-0 grid grid-cols-[84px_minmax(0,1fr)] gap-x-3 gap-y-1.5 px-4 py-3 text-[12.5px]">
        <KV label="Key">
          <span className="num">{maskedKey(cred.apiKeyPrefix)}</span>
        </KV>
        <KV label="Since">{longDay(toDate(cred.createdAt))}</KV>
        <KV label="Sessions">{sessionsLine(running, stopped)}</KV>
        <KV label="Checked">
          {check ? (
            <span className={check.valid ? undefined : 'text-risk'}>
              {check.valid ? 'Accepted' : 'Rejected'} at {etTime(check.at)}
            </span>
          ) : (
            <span className="text-fg-3">Not from this browser</span>
          )}{' '}
          <button
            type="button"
            className="text-[12px] text-fg-2 underline decoration-line-strong underline-offset-[3px] hover:text-fg"
            onClick={() => setCheckOpen((v) => !v)}
            aria-expanded={checkOpen}
          >
            {checkOpen ? 'Close' : 'Check the keys'}
          </button>
        </KV>
      </dl>
      {!cred.isActive && (
        <p className="m-0 border-t border-line px-4 py-2 text-[12px] text-risk">
          The stored keys are switched off.
        </p>
      )}
      {checkOpen && (
        <CheckForm
          prefix={cred.apiKeyPrefix}
          isPaper={cred.isPaper}
          onDone={(result) => {
            onChecked(result);
            setCheckOpen(false);
          }}
        />
      )}
    </section>
  );
}

/** Lists the connected accounts, each with its own confirm, so the wrong one isn't removed. */
function DisconnectDialog({
  open,
  onClose,
  accounts,
}: {
  open: boolean;
  onClose: () => void;
  accounts: ReadonlyArray<{ kind: AccountKind; cred: AlpacaCredentialsListItem }>;
}) {
  const remove = useBrokerStore((s) => s.remove);
  const [removing, setRemoving] = useState<string | null>(null);

  const disconnect = async (id: string) => {
    setRemoving(id);
    const ok = await remove(id);
    setRemoving(null);
    if (ok) onClose();
  };

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Disconnect an account"
      footer={
        <button type="button" className="btn btn-secondary" onClick={onClose}>
          Keep both connected
        </button>
      }
    >
      <p className="m-0 mb-3 text-[13px] text-fg-2">
        LlamaTrade removes the stored key. It can&apos;t happen while a session or a funded sleeve
        still uses it, so stop those first. Positions stay in your Alpaca account.
      </p>
      <div className="grid gap-2">
        {accounts.map(({ kind, cred }) => (
          <div
            key={cred.id}
            className="flex items-center gap-2.5 rounded-[8px] border border-line px-3 py-2 text-[13px]"
          >
            <ModeBadge mode={kind} size="sm" />
            <span className="num text-fg-2">
              {maskedAccount(cred.accountNumber) || maskedKey(cred.apiKeyPrefix)}
            </span>
            <button
              type="button"
              className="btn btn-danger btn-sm ml-auto"
              disabled={removing !== null}
              onClick={() => {
                disconnect(cred.id).catch(() => setRemoving(null));
              }}
            >
              {removing === cred.id ? 'Disconnecting…' : `Disconnect ${kind}`}
            </button>
          </div>
        ))}
      </div>
    </Dialog>
  );
}

const DOT: Record<BrokerEvent['tone'], string> = {
  ok: 'bg-accent',
  risk: 'bg-risk',
  plain: 'shadow-[inset_0_0_0_1.5px_rgb(var(--fg-3))]',
};

const logTime = (d: Date) => {
  const day = d.toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    timeZone: 'America/New_York',
  });
  return `${day} ${etTime(d).replace(' ET', '')}`;
};

/** The dated history beside the accounts, limited to what the app actually knows (broker2 D). */
function History({ events }: { events: readonly BrokerEvent[] }) {
  const [filter, setFilter] = useState<LogFilter>('all');
  const shown = filterEvents(events, filter);
  return (
    <section aria-label="History" className="panel min-w-0 overflow-hidden">
      <header className="flex min-h-[46px] items-center gap-2.5 border-b border-line px-4 py-2">
        <b className="text-[13px] font-semibold">History</b>
        <Segmented
          className="ml-auto"
          label="Show"
          value={filter}
          onChange={setFilter}
          options={[
            { key: 'all', label: 'All' },
            { key: 'paper', label: 'Paper' },
            { key: 'live', label: 'Live' },
          ]}
        />
      </header>
      {shown.length === 0 ? (
        <p className="m-0 px-4 py-4 text-[12.5px] text-fg-3">Nothing here yet.</p>
      ) : (
        <ol className="m-0 list-none p-0">
          {shown.map((e) => (
            <li
              key={e.id}
              className="grid grid-cols-[96px_12px_minmax(0,1fr)] items-baseline gap-x-2.5 border-b border-line px-4 py-2 text-[12.5px] last:border-b-0 sm:grid-cols-[104px_12px_minmax(0,1fr)_auto]"
            >
              <span className="num text-[11.5px] text-fg-3">{logTime(e.at)}</span>
              <i aria-hidden="true" className={`h-[7px] w-[7px] rounded-full ${DOT[e.tone]}`} />
              <span className="min-w-0 text-fg">{e.text}</span>
              {e.note && (
                <span className="col-start-3 text-[11.5px] text-fg-3 sm:col-start-auto">
                  {e.note}
                </span>
              )}
            </li>
          ))}
        </ol>
      )}
      <p className="m-0 border-t border-line bg-sunk px-4 py-2.5 text-[11.5px] text-fg-3">
        LlamaTrade doesn&apos;t keep a log of broker checks yet. This lists when each account was
        connected, sessions that stopped, and checks run from this browser.
      </p>
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

/** Compact account tiles beside a dated history (broker2 D); a tile with a problem turns amber. */
export function BrokerSection() {
  const credentials = useBrokerStore((s) => s.credentials);
  const loaded = useBrokerStore((s) => s.loaded);
  const loading = useBrokerStore((s) => s.loading);
  const error = useBrokerStore((s) => s.error);
  const fetch = useBrokerStore((s) => s.fetch);
  const clearError = useBrokerStore((s) => s.clearError);
  const { health } = useSettingsSummary();
  const rows = useSessionRows();
  const [checks, setChecks] = useState<BrowserCheck[]>(() => readChecks());
  const [disconnectOpen, setDisconnectOpen] = useState(false);

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
  const connected = shown.flatMap(({ kind, cred }) => (cred ? [{ kind, cred }] : []));
  const others = credentials.filter((c) => !shown.some((s) => s.cred === c));
  const ordered = [...shown].sort((a, b) => Number(!a.cred) - Number(!b.cred));
  const events = brokerEvents(
    credentials.map((c) => ({
      id: c.id,
      isPaper: c.isPaper,
      apiKeyPrefix: c.apiKeyPrefix,
      createdAt: toDate(c.createdAt),
    })),
    checks,
    rows.map((r) => ({
      id: r.session.id,
      name: r.name,
      kind: r.session.mode === ExecutionMode.LIVE ? 'live' : 'paper',
      endedAt: toDate(r.session.endedAt),
    }))
  );

  return (
    <div className="grid gap-4">
      <div className="grid items-start gap-5 lg:grid-cols-[400px_minmax(0,1fr)]">
        <div className="grid gap-3.5">
          {ordered.map(({ kind, cred }) =>
            cred ? (
              <AccountPanel
                key={kind}
                kind={kind}
                cred={cred}
                problem={health.problems.find((p) => p.kind === kind) ?? null}
                onChecked={(c) => setChecks(recordCheck(c))}
                {...counts(kind)}
              />
            ) : (
              <NotConnected key={kind} kind={kind} />
            )
          )}
          {connected.length > 0 && (
            <div className="flex flex-wrap gap-2">
              <Link to={KEYS_PATH} className="btn btn-secondary btn-sm">
                Replace keys
              </Link>
              <button
                type="button"
                className="btn btn-ghost btn-sm"
                onClick={() => setDisconnectOpen(true)}
              >
                {connected.length === 1 ? 'Disconnect' : 'Disconnect an account'}
              </button>
            </div>
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
        </div>
        <History events={events} />
      </div>

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

      <DisconnectDialog
        open={disconnectOpen}
        onClose={() => setDisconnectOpen(false)}
        accounts={connected}
      />
    </div>
  );
}

interface CheckFormProps {
  prefix: string;
  isPaper: boolean;
  onDone: (check: BrowserCheck) => void;
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
      onDone({ at: result.at, isPaper: result.isPaper, valid: result.valid });
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
