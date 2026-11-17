import type { AlpacaCredentialsListItem } from '@llamatrade/core/proto/auth_pb';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { ArrowLeft, Check, Lock, X } from 'lucide-react';
import { useEffect, useState, type ReactNode } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { LIVE_REQUIREMENTS } from '../../components/auth/accountPaths';
import { Field, FormNote } from '../../components/auth/fields';
import { Logo, LogoMark } from '../../components/common/Logo';
import { AlpacaMark } from '../../components/settings/AlpacaMark';
import { ModeBadge, Skeleton } from '../../components/ui';
import { useDocumentTitle } from '../../hooks/useDocumentTitle';
import { maskedKey } from '../../lib/scope';
import {
  alpacaLinkErrorMessage,
  safeReturnPath,
  startAlpacaLink,
} from '../../services/alpacaOAuth';
import { useAuthStore } from '../../store/auth';

import { activeOf, type Kind } from './credentials';

type Way = 'approve' | 'keys';

const CAN = ['Place and cancel orders for your sessions', 'Read positions, orders and balances'];
const CANNOT = ['Move money in or out of Alpaca', 'See your bank or identity details'];

function StepNumber({ n, state }: { n: number; state: 'on' | 'off' | 'done' }) {
  return (
    <span
      aria-hidden="true"
      className={`num grid h-7 w-7 flex-none place-items-center rounded-full text-[12.5px] font-semibold ${
        state === 'on'
          ? 'bg-fg text-canvas'
          : state === 'done'
            ? 'bg-accent-fill text-accent-ink'
            : 'border border-line-strong text-fg-3'
      }`}
    >
      {state === 'done' ? <Check className="h-3.5 w-3.5" /> : n}
    </span>
  );
}

function CanCannot() {
  const list = (title: string, items: string[], ok: boolean) => (
    <div>
      <span className="text-[11px] font-medium text-fg-3">{title}</span>
      <ul className="m-0 mt-1.5 grid list-none gap-1.5 p-0 text-[12.5px] text-fg-2">
        {items.map((t) => (
          <li key={t} className="flex items-center gap-2">
            <span
              aria-hidden="true"
              className={`grid h-4 w-4 flex-none place-items-center rounded-full ${
                ok ? 'bg-accent-soft text-accent' : 'bg-sunk text-fg-3'
              }`}
            >
              {ok ? <Check className="h-2.5 w-2.5" /> : <X className="h-2.5 w-2.5" />}
            </span>
            {t}
          </li>
        ))}
      </ul>
    </div>
  );
  return (
    <div className="grid gap-4 sm:grid-cols-2">
      {list('LlamaTrade will be able to', CAN, true)}
      {list("It won't be able to", CANNOT, false)}
    </div>
  );
}

function WayCard({
  on,
  onPick,
  icon,
  title,
  tag,
  children,
}: {
  on: boolean;
  onPick: () => void;
  icon: ReactNode;
  title: string;
  tag?: string;
  children: ReactNode;
}) {
  return (
    <button
      type="button"
      role="radio"
      aria-checked={on}
      onClick={onPick}
      className={`grid content-start gap-1.5 rounded-[10px] border bg-panel p-3.5 text-left transition-colors ${
        on
          ? 'border-accent shadow-[0_0_0_3px_var(--accent-soft)]'
          : 'border-line-strong hover:border-fg-3'
      }`}
    >
      <span className="flex items-center gap-2">
        {icon}
        <b className="text-[13px] font-semibold">{title}</b>
        {tag && <span className="badge badge-accent ml-auto">{tag}</span>}
      </span>
      <span className="text-[12px] text-fg-3">{children}</span>
    </button>
  );
}

function KeysForm({ kind, onCancel }: { kind: Kind; onCancel?: () => void }) {
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
      name: `Alpaca ${kind}`,
      apiKey: apiKey.trim(),
      apiSecret: apiSecret.trim(),
      isPaper: kind === 'paper',
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
    <form onSubmit={handleSubmit} className="grid gap-3 rounded-[10px] bg-sunk p-4">
      <p className="m-0 text-[12.5px] text-fg-2">
        {kind === 'paper'
          ? "Use the key pair from Alpaca's paper dashboard."
          : "Use the key pair from Alpaca's live dashboard. Live keys trade real money in your Alpaca account; paper sessions never use them."}{' '}
        LlamaTrade checks the pair with Alpaca, then stores it encrypted.
      </p>
      {error && <FormNote tone="warn">{error}</FormNote>}
      <div className="grid gap-3 sm:grid-cols-2">
        <Field
          id={`${kind}-apiKey`}
          label="API key ID"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          autoComplete="off"
          spellCheck={false}
          required
        />
        <Field
          id={`${kind}-apiSecret`}
          label="Secret key"
          type="password"
          value={apiSecret}
          onChange={(e) => setApiSecret(e.target.value)}
          autoComplete="off"
          required
        />
      </div>
      <div className="flex flex-wrap gap-2.5">
        <button type="submit" className="btn btn-primary" disabled={connecting}>
          {connecting ? 'Checking with Alpaca…' : `Connect ${kind} account`}
        </button>
        {onCancel && (
          <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={connecting}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}

function Connected({ cred }: { cred: AlpacaCredentialsListItem }) {
  return (
    <div className="flex flex-wrap items-center gap-2.5 text-[12.5px] text-fg-2">
      <span className="inline-flex items-center gap-1.5 text-fg">
        <i aria-hidden="true" className="h-[7px] w-[7px] rounded-full bg-fg" />
        Connected
      </span>
      <span className="num text-fg-3">Key {maskedKey(cred.apiKeyPrefix)}</span>
      <Link to="/settings/broker" className="text-accent hover:underline">
        Manage in Broker settings
      </Link>
    </div>
  );
}

function PaperStep({
  cred,
  initialWay,
}: {
  cred: AlpacaCredentialsListItem | null;
  initialWay: Way;
}) {
  const [way, setWay] = useState<Way>(initialWay);
  const [redirecting, setRedirecting] = useState(false);
  const [startError, setStartError] = useState('');

  const continueToAlpaca = () => {
    setStartError('');
    const token = useAuthStore.getState().accessToken;
    if (!token) return setStartError('Your session has ended. Please sign in again.');
    setRedirecting(true);
    startAlpacaLink(token).catch(() => {
      setRedirecting(false);
      setStartError(
        "Alpaca sign-in couldn't be started just now. Please try again, or paste a key pair instead."
      );
    });
  };

  return (
    <div className="flex gap-3.5">
      <StepNumber n={1} state={cred ? 'done' : 'on'} />
      <div className="grid min-w-0 flex-1 gap-3.5">
        <div className="flex flex-wrap items-center gap-2.5">
          <b className="text-[14.5px] font-semibold">Paper account</b>
          <ModeBadge mode="paper" size="sm" />
          <span className="ml-auto text-[12px] text-fg-3">Simulated money</span>
        </div>
        {cred ? (
          <Connected cred={cred} />
        ) : (
          <>
            <div
              role="radiogroup"
              aria-label="How to connect"
              className="grid gap-2.5 sm:grid-cols-2"
            >
              <WayCard
                on={way === 'approve'}
                onPick={() => setWay('approve')}
                icon={<AlpacaMark size={18} />}
                title="Approve on Alpaca"
                tag="Quickest"
              >
                Sign in on Alpaca&apos;s site and choose Allow. You come back here. No keys to copy.
              </WayCard>
              <WayCard
                on={way === 'keys'}
                onPick={() => setWay('keys')}
                icon={<Lock aria-hidden="true" className="h-4 w-4 text-fg-3" />}
                title="Paste an API key pair"
              >
                Create keys in Alpaca&apos;s paper dashboard and paste both here. Good if you
                already use keys.
              </WayCard>
            </div>
            <CanCannot />
            {startError && <FormNote tone="warn">{startError}</FormNote>}
            {way === 'approve' ? (
              <div className="flex flex-wrap items-center gap-3">
                <button
                  type="button"
                  className="btn btn-primary"
                  onClick={continueToAlpaca}
                  disabled={redirecting}
                >
                  <AlpacaMark size={16} />
                  {redirecting ? 'Opening Alpaca…' : 'Continue to Alpaca'}
                </button>
                <span className="text-[12px] text-fg-3">
                  Keys are stored encrypted and never shown again in full.
                </span>
              </div>
            ) : (
              <KeysForm kind="paper" />
            )}
          </>
        )}
      </div>
    </div>
  );
}

function LiveStep({
  cred,
  paperDone,
  startOpen,
}: {
  cred: AlpacaCredentialsListItem | null;
  paperDone: boolean;
  startOpen: boolean;
}) {
  const [open, setOpen] = useState(startOpen);
  return (
    <div className="flex gap-3.5">
      <StepNumber n={2} state={cred ? 'done' : open ? 'on' : 'off'} />
      <div className="grid min-w-0 flex-1 gap-3">
        <div className="flex flex-wrap items-center gap-2.5">
          <b className="text-[14.5px] font-semibold">Live account</b>
          <ModeBadge mode="live" size="sm" />
          {!cred && !open && (
            <button
              type="button"
              className="btn btn-secondary btn-sm ml-auto"
              onClick={() => setOpen(true)}
            >
              Connect live
            </button>
          )}
        </div>
        {cred ? (
          <Connected cred={cred} />
        ) : (
          <div className="grid gap-1.5 text-[12.5px] text-fg-2">
            <p className="m-0">
              Real money. It&apos;s a separate connection so a paper session can never place a live
              order by mistake.
              {paperDone ? '' : ' You can connect it now or later from Broker settings.'}
            </p>
            <p className="m-0 text-fg-3">{LIVE_REQUIREMENTS}</p>
          </div>
        )}
        {!cred && open && <KeysForm kind="live" onCancel={() => setOpen(false)} />}
      </div>
    </div>
  );
}

/** /connect/alpaca: paper as step one with two equal ways in, live as its own step (connect-alpaca2 A). */
export default function ConnectAlpacaPage() {
  const [params] = useSearchParams();
  const next = safeReturnPath(params.get('next'));
  const returnedError = params.get('error');
  const credentials = useBrokerStore((s) => s.credentials);
  const loaded = useBrokerStore((s) => s.loaded);
  const brokerError = useBrokerStore((s) => s.error);
  const fetchCredentials = useBrokerStore((s) => s.fetch);
  useDocumentTitle('Connect Alpaca');

  useEffect(() => {
    fetchCredentials().catch(() => undefined);
  }, [fetchCredentials]);

  const paper = activeOf(credentials, 'paper');
  const live = activeOf(credentials, 'live');
  const backLabel = next === '/dashboard' ? 'Back to Home' : 'Back';

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

      <main className="mx-auto grid w-full max-w-[760px] content-start gap-4 px-4 py-8 md:py-12">
        <div className="flex items-center gap-3" aria-hidden="true">
          <LogoMark size={34} />
          <span className="w-10 border-t-2 border-dotted border-line-strong" />
          <AlpacaMark size={34} />
        </div>
        <div>
          <h1 className="m-0 text-[26px] font-semibold leading-tight tracking-[-0.02em]">
            Connect Alpaca
          </h1>
          <p className="m-0 mt-1 text-[14px] text-fg-2">
            Paper and live are separate connections. Start with paper; live can wait.
          </p>
        </div>

        {returnedError && <FormNote tone="warn">{alpacaLinkErrorMessage(returnedError)}</FormNote>}
        {brokerError && credentials.length === 0 && (
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
        )}

        {!loaded ? (
          <div className="panel-rim grid gap-3 p-5" aria-busy="true">
            <Skeleton className="h-4 w-40" />
            <Skeleton className="h-3 w-full" />
            <Skeleton className="h-3 w-2/3" />
          </div>
        ) : (
          <section aria-label="Steps" className="panel-rim grid gap-0 p-0">
            <div className="p-5">
              <PaperStep
                cred={paper}
                initialWay={params.get('method') === 'keys' ? 'keys' : 'approve'}
              />
            </div>
            <div className="border-t border-line p-5">
              <LiveStep
                cred={live}
                paperDone={paper !== null}
                startOpen={params.get('account') === 'live'}
              />
            </div>
          </section>
        )}

        {paper && (
          <div className="flex flex-wrap gap-2.5">
            <Link to={next} className="btn btn-primary">
              {next === '/dashboard' ? 'Go to Home' : 'Continue'}
            </Link>
          </div>
        )}
      </main>
    </div>
  );
}
