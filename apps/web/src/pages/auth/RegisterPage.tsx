import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { AuthSplitLayout } from '../../components/auth/AuthSplitLayout';
import { authErrorMessage } from '../../components/auth/errors';
import {
  AlpacaButton,
  Field,
  FormFoot,
  FormNote,
  LINK,
  OrDivider,
} from '../../components/auth/fields';
import { startAuthWithAlpaca } from '../../services/alpacaOAuth';
import { authClient } from '../../services/grpc-client';

function registerError(err: unknown): string {
  return authErrorMessage(err, "The account couldn't be created. Please try again.");
}

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
      await authClient.register({ tenantName, email, password });
      navigate('/login', { state: { registered: true } });
    } catch (err: unknown) {
      setError(registerError(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthSplitLayout title="Create an account" subtitle="Start building and testing strategies.">
      <form onSubmit={handleSubmit} className="grid gap-3.5">
        <FormNote>
          LlamaTrade is in a closed beta. Use the email address your invite was sent to.
        </FormNote>
        {error && <FormNote tone="warn">{error}</FormNote>}
        <Field
          id="tenantName"
          label="Workspace name"
          type="text"
          value={tenantName}
          onChange={(e) => setTenantName(e.target.value)}
          autoComplete="organization"
          required
        />
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
          help="At least 8 characters."
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          minLength={8}
          required
        />
        <button type="submit" className="btn btn-primary btn-lg w-full" disabled={loading}>
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <OrDivider />
      <AlpacaButton label="Sign up with Alpaca" onClick={startAuthWithAlpaca} disabled={loading} />
      <FormFoot>
        Already have an account?{' '}
        <Link to="/login" className={LINK}>
          Sign in
        </Link>
      </FormFoot>
    </AuthSplitLayout>
  );
}
