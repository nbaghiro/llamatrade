import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { AuthSplitLayout } from '../../components/auth/AuthSplitLayout';
import { authErrorMessage } from '../../components/auth/errors';
import { landingAfterSignIn } from '../../components/auth/landing';
import { Pill } from '../../components/ui';
import { exchangeHandoff } from '../../services/alpacaOAuth';
import { useAuthStore } from '../../store/auth';

/** Exchanges the Alpaca sign-in handoff for a session and moves straight on. */
export default function AlpacaCallbackPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);
  const [error, setError] = useState('');

  useEffect(() => {
    if (params.get('error')) {
      setError('Alpaca sign-in was cancelled or did not finish.');
      return;
    }
    const handoff = params.get('handoff');
    if (!handoff) {
      setError('This sign-in link is missing its details.');
      return;
    }
    let cancelled = false;
    exchangeHandoff(handoff)
      .then(async (session) => {
        if (cancelled) return;
        setSession(session.user, session.accessToken, session.refreshToken);
        const next = await landingAfterSignIn(session.user.id);
        if (!cancelled) navigate(next, { replace: true });
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(authErrorMessage(e, 'Sign-in did not finish.'));
      });
    return () => {
      cancelled = true;
    };
  }, [params, navigate, setSession]);

  if (!error) {
    return (
      <AuthSplitLayout title="Signing you in" subtitle="Finishing the Alpaca sign-in.">
        <span className="sr-only" role="status">
          Signing you in
        </span>
      </AuthSplitLayout>
    );
  }

  return (
    <AuthSplitLayout
      title="Sign-in didn't finish"
      subtitle={`${error} Please try again.`}
      status={<Pill tone="risk">Not signed in</Pill>}
    >
      <Link to="/login" className="btn btn-primary btn-lg w-full" replace>
        Back to sign in
      </Link>
    </AuthSplitLayout>
  );
}
