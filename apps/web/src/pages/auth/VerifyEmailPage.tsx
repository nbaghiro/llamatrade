import { Clock } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { AuthSplitLayout } from '../../components/auth/AuthSplitLayout';
import { isUnreachable } from '../../components/auth/errors';
import { FormFoot, LINK } from '../../components/auth/fields';
import { ResendLinkForm } from '../../components/auth/ResendLinkForm';
import { Pill } from '../../components/ui';
import { authClient } from '../../services/grpc-client';
import { useAuthStore } from '../../store/auth';

type VerifyState = 'verifying' | 'verified' | 'expired' | 'failed';

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
      <AuthSplitLayout
        title="Your email couldn't be confirmed just now"
        subtitle="LlamaTrade couldn't be reached. The link still works, so you can try again."
        status={<Pill tone="risk">Not confirmed</Pill>}
      >
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
      </AuthSplitLayout>
    );
  }

  if (state === 'verifying') {
    return (
      <AuthSplitLayout title="Confirming your email" subtitle="This takes a moment.">
        <span className="sr-only" role="status">
          Confirming your email address
        </span>
      </AuthSplitLayout>
    );
  }

  if (state === 'verified') {
    return (
      <AuthSplitLayout
        title="Email confirmed"
        subtitle="Your address is confirmed. Thank you."
        status={<Pill tone="accent">Confirmed</Pill>}
      >
        <Link to={signedIn ? '/dashboard' : '/login'} className="btn btn-primary btn-lg w-full">
          {signedIn ? 'Go to Home' : 'Sign in'}
        </Link>
      </AuthSplitLayout>
    );
  }

  return (
    <AuthSplitLayout
      title="This link has expired"
      subtitle="Confirmation links last seven days and work once. Enter your address and we'll send a new one."
      status={
        <Pill tone="risk">
          <Clock aria-hidden="true" className="h-3.5 w-3.5" />
          Link expired
        </Pill>
      }
    >
      <ResendLinkForm
        send={(email) => authClient.resendVerification({ email })}
        sentNote={
          <>
            <b>Check your inbox.</b> If that address has an account waiting to be confirmed, a new
            link is on its way.
          </>
        }
      />
      <FormFoot>
        <Link to="/login" className={LINK}>
          Back to sign in
        </Link>
      </FormFoot>
    </AuthSplitLayout>
  );
}
