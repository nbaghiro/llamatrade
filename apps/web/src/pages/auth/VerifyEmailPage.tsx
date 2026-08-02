import { useEffect, useRef, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { AuthSplitLayout } from '../../components/auth/AuthSplitLayout';
import { authClient } from '../../services/grpc-client';

type VerifyState = 'verifying' | 'done' | 'failed';

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const [state, setState] = useState<VerifyState>(token ? 'verifying' : 'failed');
  const [message, setMessage] = useState<string>('');
  const requested = useRef(false);

  useEffect(() => {
    if (!token || requested.current) return;
    requested.current = true;
    authClient
      .verifyEmail({ token })
      .then(() => setState('done'))
      .catch((err: unknown) => {
        setState('failed');
        setMessage(err instanceof Error ? err.message : 'Verification failed.');
      });
  }, [token]);

  return (
    <AuthSplitLayout title="Email verification" subtitle="One quick check.">
      {state === 'verifying' && <p className="font-mono text-xs text-ink/70">Verifying…</p>}
      {state === 'done' && (
        <div className="border-2 border-ink bg-green-50 px-3 py-2.5 font-mono text-xs text-ink">
          Your email is verified.{' '}
          <Link to="/login" className="font-bold text-orange-600 hover:underline">
            Sign in
          </Link>
        </div>
      )}
      {state === 'failed' && (
        <div className="border-2 border-ink bg-red-50 px-3 py-2.5 font-mono text-xs text-red-600">
          {message || 'This verification link is invalid or expired.'}
        </div>
      )}
    </AuthSplitLayout>
  );
}
