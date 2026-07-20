import { useEffect, useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { exchangeHandoff } from '../../services/alpacaOAuth';
import { useAuthStore } from '../../store/auth';

/** Landing page for the Alpaca login handoff: exchange the code, start a session. */
export default function AlpacaCallbackPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const setSession = useAuthStore((s) => s.setSession);
  const [error, setError] = useState('');

  useEffect(() => {
    if (params.get('error')) {
      setError('Alpaca sign-in was cancelled or failed.');
      return;
    }
    const handoff = params.get('handoff');
    if (!handoff) {
      setError('Missing sign-in details.');
      return;
    }
    let cancelled = false;
    exchangeHandoff(handoff)
      .then((session) => {
        if (cancelled) return;
        setSession(session.user, session.accessToken, session.refreshToken);
        navigate('/dashboard', { replace: true });
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : 'Sign-in failed.');
      });
    return () => {
      cancelled = true;
    };
  }, [params, navigate, setSession]);

  return (
    <div className="flex min-h-screen items-center justify-center p-6 text-center">
      {error ? (
        <div className="space-y-3">
          <p className="text-sm text-red-600">{error}</p>
          <button
            type="button"
            className="btn btn-secondary"
            onClick={() => navigate('/login', { replace: true })}
          >
            Back to sign in
          </button>
        </div>
      ) : (
        <p className="font-mono text-sm text-ink/60">Signing you in…</p>
      )}
    </div>
  );
}
