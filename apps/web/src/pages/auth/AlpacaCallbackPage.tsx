import { Clock } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { AuthCardLayout, CardIcon } from '../../components/auth/AuthCardLayout';
import { FormHeader } from '../../components/auth/AuthSplitLayout';
import { authErrorMessage } from '../../components/auth/errors';
import { landingAfterSignIn } from '../../components/auth/landing';
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
      <AuthCardLayout>
        <FormHeader title="Signing you in" subtitle="Finishing the Alpaca sign-in." />
        <span className="sr-only" role="status">
          Signing you in
        </span>
      </AuthCardLayout>
    );
  }

  return (
    <AuthCardLayout>
      <CardIcon tone="warn">
        <Clock />
      </CardIcon>
      <FormHeader title="Sign-in didn't finish" subtitle={`${error} Please try again.`} />
      <Link to="/login" className="btn btn-primary btn-lg w-full" replace>
        Back to sign in
      </Link>
    </AuthCardLayout>
  );
}
