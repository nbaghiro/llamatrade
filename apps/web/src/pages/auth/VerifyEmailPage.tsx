import { AlertTriangle, Clock, MailCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { AuthCardLayout, CardIcon } from '../../components/auth/AuthCardLayout';
import { FormHeader } from '../../components/auth/AuthSplitLayout';
import { isUnreachable } from '../../components/auth/errors';
import { Field, FormFoot, FormNote, LINK } from '../../components/auth/fields';
import { authClient } from '../../services/grpc-client';
import { useAuthStore } from '../../store/auth';

const FOOTNOTE = 'Paper and live trading on Alpaca';

type VerifyState = 'verifying' | 'verified' | 'expired' | 'failed';

function ResendForm() {
  const [email, setEmail] = useState(useAuthStore.getState().user?.email ?? '');
  const [state, setState] = useState<'idle' | 'sending' | 'sent' | 'failed'>('idle');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setState('sending');
    try {
      await authClient.resendVerification({ email });
      setState('sent');
    } catch {
      setState('failed');
    }
  };

  return (
    <form onSubmit={handleSubmit} className="grid gap-3.5">
      <Field
        id="email"
        label="Email address"
        type="email"
        value={email}
        onChange={(e) => {
          setEmail(e.target.value);
          if (state !== 'sending') setState('idle');
        }}
        autoComplete="email"
        required
      />
      <button
        type="submit"
        className="btn btn-primary btn-lg w-full"
        disabled={state === 'sending' || state === 'sent'}
      >
        {state === 'sending' ? 'Sending…' : state === 'sent' ? 'Link sent' : 'Send a new link'}
      </button>
      {state === 'sent' && (
        <FormNote tone="ok">
          <b>Check your inbox.</b> If that address has an account waiting to be confirmed, a new
          link is on its way.
        </FormNote>
      )}
      {state === 'failed' && (
        <FormNote tone="warn">The link couldn&apos;t be sent just now. Please try again.</FormNote>
      )}
    </form>
  );
}

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const [state, setState] = useState<VerifyState>(token ? 'verifying' : 'expired');
  const [attempt, setAttempt] = useState(0);
  const requested = useRef(-1);
  const signedIn = useAuthStore((s) => s.isAuthenticated);

  useEffect(() => {
    if (!token || requested.current === attempt) return;
    requested.current = attempt;
    authClient
      .verifyEmail({ token })
      .then(() => setState('verified'))
      .catch((err: unknown) => setState(isUnreachable(err) ? 'failed' : 'expired'));
  }, [token, attempt]);

  if (state === 'failed') {
    return (
      <AuthCardLayout footnote={FOOTNOTE}>
        <CardIcon tone="warn">
          <AlertTriangle />
        </CardIcon>
        <FormHeader
          title="Your email couldn't be confirmed just now"
          subtitle="LlamaTrade couldn't be reached. The link still works, so you can try again."
        />
        <button
          type="button"
          className="btn btn-primary btn-lg w-full"
          onClick={() => {
            setState('verifying');
            setAttempt((a) => a + 1);
          }}
        >
          Try again
        </button>
      </AuthCardLayout>
    );
  }

  if (state === 'verifying') {
    return (
      <AuthCardLayout footnote={FOOTNOTE}>
        <FormHeader title="Confirming your email" subtitle="This takes a moment." />
        <span className="sr-only" role="status">
          Confirming your email address
        </span>
      </AuthCardLayout>
    );
  }

  if (state === 'verified') {
    return (
      <AuthCardLayout footnote={FOOTNOTE}>
        <CardIcon tone="ok">
          <MailCheck />
        </CardIcon>
        <FormHeader title="Email confirmed" subtitle="Your address is confirmed. Thank you." />
        <Link to={signedIn ? '/dashboard' : '/login'} className="btn btn-primary btn-lg w-full">
          {signedIn ? 'Go to Home' : 'Sign in'}
        </Link>
      </AuthCardLayout>
    );
  }

  return (
    <AuthCardLayout footnote={FOOTNOTE}>
      <CardIcon tone="warn">
        <Clock />
      </CardIcon>
      <FormHeader
        title="This link has expired"
        subtitle="Confirmation links last seven days and work once. Enter your address and we'll send a new one."
      />
      <ResendForm />
      <FormFoot>
        <Link to="/login" className={LINK}>
          Back to sign in
        </Link>
      </FormFoot>
    </AuthCardLayout>
  );
}
