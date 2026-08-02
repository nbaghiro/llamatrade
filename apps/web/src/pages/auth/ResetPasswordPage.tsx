import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { AuthSplitLayout } from '../../components/auth/AuthSplitLayout';
import { authClient } from '../../services/grpc-client';

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const token = searchParams.get('token') ?? '';
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (password !== confirm) {
      setError('Passwords do not match.');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      await authClient.resetPassword({ token, newPassword: password });
      navigate('/login', { replace: true });
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Reset failed; the link may have expired.');
    } finally {
      setLoading(false);
    }
  };

  if (!token) {
    return (
      <AuthSplitLayout title="Reset your password" subtitle="This link is incomplete.">
        <p className="font-mono text-xs text-ink/70">
          Open the link from your email, or{' '}
          <Link to="/forgot-password" className="font-bold text-orange-600 hover:underline">
            request a new one
          </Link>
          .
        </p>
      </AuthSplitLayout>
    );
  }

  return (
    <AuthSplitLayout title="Choose a new password" subtitle="Every existing session will be signed out.">
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
          <label className="label" htmlFor="password">
            New password
          </label>
          <input
            id="password"
            type="password"
            className="input"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            required
          />
        </div>
        <div>
          <label className="label" htmlFor="confirm">
            Confirm password
          </label>
          <input
            id="confirm"
            type="password"
            className="input"
            placeholder="••••••••"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            autoComplete="new-password"
            required
          />
        </div>
        <button type="submit" className="btn btn-primary btn-lg w-full" disabled={loading}>
          {loading ? 'Resetting…' : 'Reset password'}
        </button>
      </form>
    </AuthSplitLayout>
  );
}
