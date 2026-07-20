import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';

import { completeAlpacaSignup } from '../../services/alpacaOAuth';
import { useAuthStore } from '../../store/auth';

/** Capture the email/password OAuth can't provide, then finish sign-up-with-Alpaca. */
export default function CompleteSignupPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const ticket = params.get('ticket') || '';
  const setSession = useAuthStore((s) => s.setSession);

  const [email, setEmail] = useState('');
  const [firstName, setFirstName] = useState('');
  const [lastName, setLastName] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!ticket) {
      setError('Missing sign-up ticket. Please start again from sign in.');
      return;
    }
    setLoading(true);
    setError('');
    try {
      const session = await completeAlpacaSignup({ ticket, email, password, firstName, lastName });
      setSession(session.user, session.accessToken, session.refreshToken);
      navigate('/dashboard', { replace: true });
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Could not complete sign up.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center p-6">
      <form onSubmit={handleSubmit} className="w-full max-w-sm space-y-4">
        <div>
          <h1 className="text-xl font-bold">Finish creating your account</h1>
          <p className="mt-1 text-sm text-ink/60">
            Your Alpaca account is connected — add your details to finish.
          </p>
        </div>
        {error && <p className="text-sm text-red-600">{error}</p>}
        <input
          className="input"
          type="email"
          placeholder="Email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          required
        />
        <div className="flex gap-3">
          <input
            className="input"
            placeholder="First name"
            value={firstName}
            onChange={(e) => setFirstName(e.target.value)}
          />
          <input
            className="input"
            placeholder="Last name"
            value={lastName}
            onChange={(e) => setLastName(e.target.value)}
          />
        </div>
        <input
          className="input"
          type="password"
          placeholder="Password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
          minLength={8}
        />
        <button type="submit" className="btn btn-primary btn-lg w-full" disabled={loading}>
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>
    </div>
  );
}
