import { useState } from 'react';
import { Link } from 'react-router-dom';

import { AuthSplitLayout } from '../../components/auth/AuthSplitLayout';
import { authClient } from '../../services/grpc-client';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setError(null);
    try {
      await authClient.requestPasswordReset({ email });
      setSent(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Something went wrong; try again.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthSplitLayout title="Reset your password" subtitle="We will email you a reset link.">
      {sent ? (
        <div className="border-2 border-ink bg-green-50 px-3 py-2.5 font-mono text-xs text-ink">
          If that email has an account, a reset link is on its way. Check your inbox.
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="space-y-4">
          {error && (
            <div
              className="border-2 border-ink bg-red-50 px-3 py-2.5 font-mono text-xs text-red-600"
              role="alert"
            >
              {error}
            </div>
          )}
          <div>
            <label className="label" htmlFor="email">
              Email address
            </label>
            <input
              id="email"
              type="email"
              className="input"
              placeholder="you@example.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              autoComplete="email"
              required
            />
          </div>
          <button type="submit" className="btn btn-primary btn-lg w-full" disabled={loading}>
            {loading ? 'Sending…' : 'Send reset link'}
          </button>
        </form>
      )}

      <p className="mt-6 font-mono text-[11px] uppercase tracking-wide text-ink/60">
        Remembered it?{' '}
        <Link to="/login" className="font-bold text-orange-600 underline-offset-2 hover:underline">
          Sign in
        </Link>
      </p>
    </AuthSplitLayout>
  );
}
