import type { AlpacaCredentialsListItem } from '@llamatrade/core/proto/auth_pb';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { ArrowLeft, Check, ExternalLink, Landmark, Minus } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { Field, FormNote } from '../../components/auth/fields';
import { Logo, LogoMark } from '../../components/common/Logo';
import { Skeleton } from '../../components/ui';
import {
  alpacaLinkErrorMessage,
  safeReturnPath,
  startAlpacaLink,
} from '../../services/alpacaOAuth';
import { useAuthStore } from '../../store/auth';

type Stage = 'before' | 'connecting' | 'connected';

const CAN = [
  'Read your balance and positions',
  'Place and cancel orders for your sessions',
  'Read fills, which keep the ledger right',
];
const CANNOT = [
  'Move money in or out of Alpaca',
  'Trade with real money in the beta',
  'See your Alpaca password',
];

function activePaper(credentials: readonly AlpacaCredentialsListItem[]) {
  return credentials.find((c) => c.isPaper && c.isActive) ?? null;
}

function Tiles({ stage, workspace }: { stage: Stage; workspace: string }) {
  const wire =
    stage === 'connected'
      ? 'border-solid border-accent'
      : stage === 'connecting'
        ? 'border-dotted border-accent motion-safe:animate-pulse'
        : 'border-dotted border-line-strong';
  const tile =
    'grid h-[76px] w-[112px] content-center justify-items-center gap-[3px] rounded-[12px] border border-line-strong bg-panel text-[13px] sm:h-[92px] sm:w-[132px]';
  return (
    <div className="flex items-center" aria-hidden="true">
      <span className={tile}>
        <LogoMark size={22} />
        <b className="font-semibold">LlamaTrade</b>
        <span className="max-w-[104px] truncate text-[11px] text-fg-3">{workspace}</span>
      </span>
      <span className={`relative w-12 border-t-2 sm:w-[120px] ${wire}`}>
        {stage === 'connected' && (
          <span className="absolute left-1/2 top-1/2 grid h-5 w-5 -translate-x-1/2 -translate-y-1/2 place-items-center rounded-full bg-accent-fill text-accent-ink">
            <Check className="h-3 w-3" />
          </span>
        )}
      </span>
      <span className={tile}>
        <Landmark className="h-[22px] w-[22px] text-fg" />
        <b className="font-semibold">Alpaca</b>
        <span className="text-[11px] text-fg-3">Paper account</span>
      </span>
    </div>
  );
}

function CanCannot() {
  const list = (items: string[], ok: boolean) => (
    <ul className="m-0 mt-2 grid list-none gap-[7px] p-0 text-[12.5px] text-fg-2">
      {items.map((t) => (
        <li key={t} className="flex items-center gap-2">
          {ok ? (
            <Check aria-hidden="true" className="h-4 w-4 flex-none text-accent" />
          ) : (
            <Minus aria-hidden="true" className="h-4 w-4 flex-none text-fg-3" />
          )}
          {t}
        </li>
      ))}
    </ul>
  );
  return (
    <div className="grid w-full max-w-[640px] gap-5 rounded-[10px] border border-line bg-panel px-[22px] py-[18px] text-left sm:grid-cols-2 sm:gap-7">
      <div>
        <b className="text-[13px] font-semibold">LlamaTrade will be able to</b>
        {list(CAN, true)}
      </div>
      <div>
        <b className="text-[13px] font-semibold">LlamaTrade won&apos;t be able to</b>
        {list(CANNOT, false)}
      </div>
    </div>
  );
}

function PaperOnly() {
  return (
    <div className="flex flex-wrap items-center justify-center gap-2.5">
      <span className="inline-flex gap-0.5 rounded-[6px] bg-sunk p-0.5 text-[11.5px]">
        <span className="rounded-[4px] bg-panel px-[9px] py-[3px] text-fg shadow-[0_0_0_1px_rgb(var(--line-strong))]">
          Paper
        </span>
        <span aria-disabled="true" className="px-[9px] py-[3px] text-fg-2 opacity-45">
          Live
        </span>
      </span>
      <span className="text-[12px] text-fg-3">Live trading isn&apos;t available in the beta.</span>
    </div>
  );
}

function KeysForm({ onCancel }: { onCancel: () => void }) {
  const connect = useBrokerStore((s) => s.connect);
  const connecting = useBrokerStore((s) => s.connecting);
  const error = useBrokerStore((s) => s.error);
  const clearError = useBrokerStore((s) => s.clearError);
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');

  useEffect(() => {
    clearError();
    return clearError;
  }, [clearError]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    connect({
      name: 'Alpaca paper',
      apiKey: apiKey.trim(),
      apiSecret: apiSecret.trim(),
      isPaper: true,
    })
      .then((ok) => {
        if (ok) {
          setApiKey('');
          setApiSecret('');
        }
      })
      .catch(() => undefined);
  };

  return (
    <form
      onSubmit={handleSubmit}
      className="grid w-full max-w-[420px] gap-3.5 rounded-[10px] border border-line bg-panel p-5 text-left"
    >
      <p className="m-0 text-[12.5px] text-fg-2">
        Use the key pair from your Alpaca paper dashboard. LlamaTrade checks it with Alpaca, then
        stores it encrypted.
      </p>
      {error && <FormNote tone="warn">{error}</FormNote>}
      <Field
        id="apiKey"
        label="API key ID"
        value={apiKey}
        onChange={(e) => setApiKey(e.target.value)}
        autoComplete="off"
        spellCheck={false}
        required
      />
      <Field
        id="apiSecret"
        label="Secret key"
        type="password"
        value={apiSecret}
        onChange={(e) => setApiSecret(e.target.value)}
        autoComplete="off"
        required
      />
      <div className="flex flex-wrap gap-2.5">
        <button type="submit" className="btn btn-primary" disabled={connecting}>
          {connecting ? 'Checking with Alpaca…' : 'Connect paper account'}
        </button>
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={connecting}>
          Cancel
        </button>
      </div>
    </form>
  );
}

/**
 * /connect/alpaca: one page for the whole round trip. It explains what LlamaTrade can and can't
 * do, sends the person to Alpaca, and shows the connection once they come back.
 */
export default function ConnectAlpacaPage() {
  const [params] = useSearchParams();
  const next = safeReturnPath(params.get('next'));
  const returnedError = params.get('error');
  const user = useAuthStore((s) => s.user);
  const credentials = useBrokerStore((s) => s.credentials);
  const loaded = useBrokerStore((s) => s.loaded);
  const fetchCredentials = useBrokerStore((s) => s.fetch);
  const keysConnecting = useBrokerStore((s) => s.connecting);
  const brokerError = useBrokerStore((s) => s.error);

  const [redirecting, setRedirecting] = useState(false);
  const [startError, setStartError] = useState('');
  const [showKeys, setShowKeys] = useState(false);

  useEffect(() => {
    fetchCredentials().catch(() => undefined);
  }, [fetchCredentials]);

  const paper = activePaper(credentials);
  const stage: Stage = paper
    ? 'connected'
    : redirecting || keysConnecting
      ? 'connecting'
      : 'before';
  const workspace =
    [user?.firstName, user?.lastName].filter(Boolean).join(' ') || user?.email || 'Your account';
  const backLabel = next === '/dashboard' ? 'Back to Home' : 'Back';

  const continueToAlpaca = async () => {
    setStartError('');
    const token = useAuthStore.getState().accessToken;
    if (!token) {
      setStartError('Your session has ended. Please sign in again.');
      return;
    }
    setRedirecting(true);
    try {
      await startAlpacaLink(token);
    } catch {
      setRedirecting(false);
      setStartError(
        "Alpaca sign-in couldn't be started just now. Please try again, or paste API keys instead."
      );
    }
  };

  return (
    <div className="flex min-h-screen flex-col bg-canvas">
      <header className="flex h-14 flex-none items-center justify-between border-b border-line px-4 md:px-[26px]">
        <Link to="/dashboard" aria-label="LlamaTrade Home">
          <Logo size={22} showText />
        </Link>
        <Link
          to={next}
          className="inline-flex items-center gap-1 text-[13px] text-accent hover:underline"
        >
          <ArrowLeft aria-hidden="true" className="h-4 w-4" />
          {backLabel}
        </Link>
      </header>

      <main className="grid flex-1 grid-cols-[minmax(0,1fr)] content-center justify-items-center gap-[18px] px-4 py-8 text-center md:p-5">
        <Tiles stage={stage} workspace={workspace} />

        {!loaded && !paper ? (
          <div className="grid w-full max-w-[560px] justify-items-center gap-3" aria-hidden="true">
            <Skeleton className="h-7 w-80 max-w-full" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        ) : stage === 'connected' && paper ? (
          <>
            <h1 className="m-0 text-[22px] font-semibold leading-tight tracking-[-0.02em] sm:text-[26px]">
              Alpaca paper account connected
            </h1>
            <p className="m-0 max-w-[560px] text-fg-2">
              Sessions you deploy will place paper orders in this account, and Alpaca holds the
              funds. You can manage or disconnect it in Settings.
            </p>
            <div className="flex w-full max-w-[420px] items-center justify-between gap-3 rounded-[10px] border border-line bg-panel px-4 py-3 text-left text-[12.5px]">
              <span className="min-w-0">
                <b className="block truncate font-semibold">{paper.name || 'Alpaca paper'}</b>
                <span className="num text-fg-3">Key {paper.apiKeyPrefix}…</span>
              </span>
              <span className="badge uppercase tracking-[0.05em]">Paper</span>
            </div>
            <div className="flex flex-wrap justify-center gap-2.5">
              <Link to={next} className="btn btn-primary btn-lg">
                {next === '/dashboard' ? 'Go to Home' : 'Continue'}
              </Link>
              <Link to="/settings/broker" className="btn btn-secondary btn-lg">
                Manage in Settings
              </Link>
            </div>
          </>
        ) : stage === 'connecting' ? (
          <>
            <h1 className="m-0 text-[22px] font-semibold leading-tight tracking-[-0.02em] sm:text-[26px]">
              Connecting to Alpaca
            </h1>
            <p className="m-0 max-w-[560px] text-fg-2" role="status">
              {redirecting
                ? "Taking you to Alpaca's site to sign in. You'll come back here when it's done."
                : 'Checking the keys with Alpaca.'}
            </p>
            {showKeys && <KeysForm onCancel={() => setShowKeys(false)} />}
          </>
        ) : (
          <>
            <h1 className="m-0 text-[22px] font-semibold leading-tight tracking-[-0.02em] sm:text-[26px]">
              Connect your Alpaca paper account
            </h1>
            <p className="m-0 max-w-[560px] text-fg-2">
              Sessions place orders in your own Alpaca account, and Alpaca holds the funds.
              You&apos;ll sign in on Alpaca&apos;s site and come back here.
            </p>
            {brokerError && !showKeys && credentials.length === 0 && (
              <div className="w-full max-w-[640px] text-left">
                <FormNote tone="warn">
                  We couldn&apos;t check whether an Alpaca account is already connected.{' '}
                  <button
                    type="button"
                    className="text-accent underline-offset-2 hover:underline"
                    onClick={() => fetchCredentials().catch(() => undefined)}
                  >
                    Check again
                  </button>
                </FormNote>
              </div>
            )}
            {(startError || returnedError) && (
              <div className="w-full max-w-[640px] text-left">
                <FormNote tone="warn">
                  {startError || alpacaLinkErrorMessage(returnedError ?? '')}
                </FormNote>
              </div>
            )}
            <CanCannot />
            <PaperOnly />
            {showKeys ? (
              <KeysForm onCancel={() => setShowKeys(false)} />
            ) : (
              <div className="flex w-full flex-col gap-2.5 sm:w-auto sm:flex-row">
                <button
                  type="button"
                  className="btn btn-primary btn-lg"
                  onClick={() => continueToAlpaca().catch(() => undefined)}
                >
                  <ExternalLink aria-hidden="true" className="h-4 w-4" />
                  Continue to Alpaca
                </button>
                <button
                  type="button"
                  className="btn btn-secondary btn-lg"
                  onClick={() => setShowKeys(true)}
                >
                  Paste API keys instead
                </button>
              </div>
            )}
          </>
        )}
      </main>
    </div>
  );
}
