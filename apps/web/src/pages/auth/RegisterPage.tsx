import { ConnectError } from '@connectrpc/connect';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { AuthSplitLayout } from '../../components/auth/AuthSplitLayout';
import { SocialAuthButtons } from '../../components/auth/SocialAuthButtons';
import { authClient } from '../../services/grpc-client';

export default function RegisterPage() {
  const navigate = useNavigate();

  const [tenantName, setTenantName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);

    try {
      await authClient.register({
        tenantName,
        email,
        password,
      });
      navigate('/login', { state: { registered: true } });
    } catch (err: unknown) {
      if (err instanceof ConnectError) {
        setError(err.message || 'Registration failed');
      } else {
        setError('Registration failed');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthSplitLayout title="Create Account" subtitle="Start building your trading strategies">
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
          <label className="label" htmlFor="tenantName">
            Company / Project name
          </label>
          <input
            id="tenantName"
            type="text"
            className="input"
            placeholder="Acme Capital"
            value={tenantName}
            onChange={(e) => setTenantName(e.target.value)}
            autoComplete="organization"
            required
          />
        </div>

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
            placeholder="Min 8 characters"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="new-password"
            minLength={8}
            required
          />
        </div>

        <button type="submit" className="btn btn-primary btn-lg w-full" disabled={loading}>
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>

      <SocialAuthButtons disabled={loading} />

      <p className="mt-6 font-mono text-[11px] uppercase tracking-wide text-ink/60">
        Already have an account?{' '}
        <Link to="/login" className="font-bold text-orange-600 underline-offset-2 hover:underline">
          Sign in
        </Link>
      </p>
    </AuthSplitLayout>
  );
}
