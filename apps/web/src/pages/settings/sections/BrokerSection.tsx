import { toDate } from '@llamatrade/core/format';
import { useBillingStore } from '@llamatrade/core/stores/billing';
import { useBrokerStore, type CredentialCheck } from '@llamatrade/core/stores/broker';
import { AlertTriangle, Check, Info, Minus, PlugZap } from 'lucide-react';
import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { Dialog, EmptyState, PanelError, Skeleton, StatusMark } from '../../../components/ui';
import { asSentence } from '../../../lib/format';
import { describeOpen } from '../../../lib/marketClock';
import { keyMismatch, maskedKey, primaryCredential } from '../model';
import { KV, ListRow, Note, Panel } from '../parts';

const CONNECT_PATH = '/connect/alpaca?next=/settings/broker';

function CheckMark({ state }: { state: 'pass' | 'fail' | 'unknown' }) {
  if (state === 'pass') return <Check aria-label="Passed" className="h-4 w-4 text-accent" />;
  if (state === 'fail') return <AlertTriangle aria-label="Failed" className="h-4 w-4 text-risk" />;
  return <Minus aria-label="Not checked" className="h-4 w-4 text-fg-3" />;
}

function checkSummary(check: CredentialCheck | null, now: Date): ReactNode {
  if (!check) return 'Not checked from this browser yet.';
  const when = describeOpen(check.at, now);
  return check.valid ? (
    <span className="num">{when}, passed</span>
  ) : (
    <span className="num text-risk">
      {when}, {check.message}
    </span>
  );
}

export function BrokerSection() {
  const credentials = useBrokerStore((s) => s.credentials);
  const loaded = useBrokerStore((s) => s.loaded);
  const loading = useBrokerStore((s) => s.loading);
  const error = useBrokerStore((s) => s.error);
  const lastCheck = useBrokerStore((s) => s.lastCheck);
  const fetch = useBrokerStore((s) => s.fetch);
  const remove = useBrokerStore((s) => s.remove);
  const clearError = useBrokerStore((s) => s.clearError);
  const running = useBillingStore((s) => s.usageCounts?.liveSessions ?? null);
  const fetchUsageCounts = useBillingStore((s) => s.fetchUsageCounts);
  const [checkOpen, setCheckOpen] = useState(false);
  const [confirmOpen, setConfirmOpen] = useState(false);
  const [removing, setRemoving] = useState(false);

  useEffect(() => {
    fetch().catch(() => undefined);
    fetchUsageCounts().catch(() => undefined);
  }, [fetch, fetchUsageCounts]);

  const cred = primaryCredential(credentials);
  const others = credentials.filter((c) => c !== cred);

  if (!loaded || (loading && credentials.length === 0)) {
    return (
      <div className="grid gap-3" aria-busy="true">
        <Panel title={<Skeleton className="h-3 w-28" />}>
          <div className="grid gap-3 px-3.5 py-4">
            <Skeleton className="h-2.5 w-2/3" />
            <Skeleton className="h-2.5 w-1/2" />
            <Skeleton className="h-2.5 w-3/5" />
          </div>
        </Panel>
      </div>
    );
  }

  if (!cred) {
    if (error) {
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
    return (
      <section className="panel">
        <EmptyState
          icon={PlugZap}
          title="No broker connected"
          body="Backtests don't need a broker. Connect your Alpaca paper account when you want to run a paper session."
          actions={
            <Link to={CONNECT_PATH} className="btn btn-primary">
              Connect Alpaca
            </Link>
          }
        />
      </section>
    );
  }

  const label = cred.isPaper ? 'Alpaca paper' : 'Alpaca live';
  const created = toDate(cred.createdAt);
  const sessionsLine =
    running === null ? null : running === 1 ? 'one running session' : `${running} running sessions`;

  const disconnect = async () => {
    setRemoving(true);
    await remove(cred.id);
    setRemoving(false);
    setConfirmOpen(false);
  };

  return (
    <div className="grid gap-3">
      <Panel
        title={label}
        aside={
          cred.isActive ? (
            <StatusMark state="running" label="Connected" />
          ) : (
            <StatusMark state="error" label="Inactive" />
          )
        }
      >
        <div className="grid gap-x-7 px-3.5 py-3 sm:grid-cols-2">
          <KV label="Name">{cred.name || 'Alpaca account'}</KV>
          <KV label="Key">
            <span className="num">{maskedKey(cred.apiKeyPrefix)}</span>
          </KV>
          <KV label="Account">{cred.isPaper ? 'Paper' : 'Live'}</KV>
          <KV label="Market data">IEX feed</KV>
          <KV label="Connected on">
            {created
              ? created.toLocaleDateString('en-US', {
                  month: 'short',
                  day: 'numeric',
                  year: 'numeric',
                })
              : 'Not available'}
          </KV>
          <KV label="Sessions running">{running === null ? '…' : running}</KV>
        </div>
      </Panel>

      <Panel title="Checks" aside="from this browser">
        <ListRow
          lead={<CheckMark state={cred.isActive ? 'pass' : 'fail'} />}
          title="Keys stored and active"
          sub={
            cred.isActive
              ? 'LlamaTrade holds these keys encrypted.'
              : 'These keys are switched off.'
          }
        />
        <ListRow
          lead={<CheckMark state={cred.isPaper ? 'pass' : 'fail'} />}
          title="Account is paper"
          sub={
            cred.isPaper
              ? 'Orders go to Alpaca paper trading.'
              : "Live trading isn't available in the beta."
          }
        />
        <ListRow
          lead={
            <CheckMark state={lastCheck === null ? 'unknown' : lastCheck.valid ? 'pass' : 'fail'} />
          }
          title="Credentials accepted by Alpaca"
          sub={checkSummary(lastCheck, new Date())}
          end={
            <button
              type="button"
              className="btn btn-secondary btn-sm"
              onClick={() => setCheckOpen((v) => !v)}
              aria-expanded={checkOpen}
            >
              Check now
            </button>
          }
        />
        {checkOpen && (
          <CheckForm
            prefix={cred.apiKeyPrefix}
            isPaper={cred.isPaper}
            onDone={() => setCheckOpen(false)}
          />
        )}
      </Panel>

      {others.length > 0 && (
        <Panel title="Other stored keys">
          {others.map((c) => (
            <ListRow
              key={c.id}
              title={c.name || 'Alpaca account'}
              sub={
                <span className="num">
                  {maskedKey(c.apiKeyPrefix)} · {c.isPaper ? 'Paper' : 'Live'}
                  {c.isActive ? '' : ' · inactive'}
                </span>
              }
            />
          ))}
        </Panel>
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

      <Note icon={<Info className="h-4 w-4" />}>
        Disconnecting removes these keys from LlamaTrade. It can&apos;t happen while{' '}
        {sessionsLine ? `${sessionsLine} or a funded sleeve` : 'a session or a funded sleeve'} still
        uses them, so stop those first. Positions stay in your Alpaca account.
      </Note>

      <div className="flex flex-wrap justify-end gap-2">
        <Link to={CONNECT_PATH} className="btn btn-secondary">
          Reconnect
        </Link>
        <button type="button" className="btn btn-danger" onClick={() => setConfirmOpen(true)}>
          Disconnect
        </button>
      </div>

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
          LlamaTrade removes the key {maskedKey(cred.apiKeyPrefix)}. Paper sessions can&apos;t place
          orders until you connect again. Positions stay in your Alpaca account.
        </p>
      </Dialog>
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
      className="grid gap-2.5 border-t border-line bg-sunk px-3.5 py-3"
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
