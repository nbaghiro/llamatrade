import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import { AuthSplitLayout } from '../../components/auth/AuthSplitLayout';
import { signInError } from '../../components/auth/errors';
import {
  AlpacaButton,
  Field,
  FormFoot,
  FormNote,
  LINK,
  OrDivider,
} from '../../components/auth/fields';
import { landingAfterSignIn } from '../../components/auth/landing';
import { startAuthWithAlpaca } from '../../services/alpacaOAuth';
import { authClient } from '../../services/grpc-client';
import { useAuthStore } from '../../store/auth';

export default function LoginPage() {
  const navigate = useNavigate();
  const location = useLocation();
  const registered = (location.state as { registered?: boolean } | null)?.registered === true;
  const setSession = useAuthStore((state) => state.setSession);

  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [passwordError, setPasswordError] = useState('');
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setPasswordError('');
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
      navigate(await landingAfterSignIn(user.id), { replace: true });
    } catch (err: unknown) {
      const shown = signInError(err);
      setError(shown.form);
      setPasswordError(shown.field);
      setLoading(false);
    }
  };

  return (
    <AuthSplitLayout title="Sign in" subtitle="Welcome back to LlamaTrade.">
      <form onSubmit={handleSubmit} className="grid gap-3.5">
        {registered && !error && !passwordError && (
          <FormNote tone="ok">
            <b>Your account is ready.</b> We&apos;ve emailed you a link to confirm your address. You
            can sign in now.
          </FormNote>
        )}
        {error && <FormNote tone="warn">{error}</FormNote>}
        <Field
          id="email"
          label="Email address"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
        />
        <Field
          id="password"
          label="Password"
          aside={
            <Link to="/forgot-password" className={LINK}>
              Forgot password?
            </Link>
          }
          type="password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            setPasswordError('');
          }}
          error={passwordError || undefined}
          autoComplete="current-password"
          required
        />
        <button type="submit" className="btn btn-primary btn-lg w-full" disabled={loading}>
          {loading ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
      <OrDivider />
      <AlpacaButton label="Continue with Alpaca" onClick={startAuthWithAlpaca} disabled={loading} />
      <FormFoot>
        Have an invite?{' '}
        <Link to="/register" className={LINK}>
          Create an account
        </Link>
      </FormFoot>
    </AuthSplitLayout>
  );
}
