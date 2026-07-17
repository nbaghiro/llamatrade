import { ConnectError } from '@connectrpc/connect';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { AuthSplitLayout } from '../../components/auth/AuthSplitLayout';
import { SocialAuthButtons } from '../../components/auth/SocialAuthButtons';
import { authClient } from '../../services/grpc-client';
import { useAuthStore } from '../../store/auth';

export default function LoginPage() {
  const navigate = useNavigate();
  const setSession = useAuthStore((state) => state.setSession);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      const response = await authClient.login({ email, password });

      const user = {
        id: response.user?.id ?? '',
        email: response.user?.email ?? '',
        firstName: response.user?.firstName ?? '',
        lastName: response.user?.lastName ?? '',
        avatarUrl: response.user?.avatarUrl ?? '',
        roles: response.user?.roles ?? [],
        tenantId: response.user?.tenantId ?? '',
      };

      setSession(user, response.accessToken, response.refreshToken);
      navigate('/dashboard');
    } catch (err: unknown) {
      if (err instanceof ConnectError) {
        setError(err.message || 'Login failed');
      } else {
        setError('Login failed');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthSplitLayout title="Sign In" subtitle="Welcome back — access your account">
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

        <div>
          <label className="label" htmlFor="password">
            Password
          </label>
          <input
            id="password"
            type="password"
            className="input"
            placeholder="••••••••"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
          />
        </div>

        <button type="submit" className="btn btn-primary btn-lg w-full" disabled={loading}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>

      <SocialAuthButtons disabled={loading} />

      <p className="mt-6 font-mono text-[11px] uppercase tracking-wide text-ink/60">
        No account?{' '}
        <Link
          to="/register"
          className="font-bold text-orange-600 underline-offset-2 hover:underline"
        >
          Sign up
        </Link>
      </p>
    </AuthSplitLayout>
  );
}
