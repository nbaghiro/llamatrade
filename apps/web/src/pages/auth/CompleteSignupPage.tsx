import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { AuthCardLayout } from '../../components/auth/AuthCardLayout';
import { FormHeader } from '../../components/auth/AuthSplitLayout';
import { authErrorMessage } from '../../components/auth/errors';
import { Field, FormNote, LINK } from '../../components/auth/fields';
import { landingAfterSignIn } from '../../components/auth/landing';
import { completeAlpacaSignup } from '../../services/alpacaOAuth';
import { useAuthStore } from '../../store/auth';

/** Collects the email, name and password Alpaca sign-in can't provide, then creates the account. */
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
    setLoading(true);
    setError('');
    try {
      const session = await completeAlpacaSignup({ ticket, email, password, firstName, lastName });
      setSession(session.user, session.accessToken, session.refreshToken);
      navigate(await landingAfterSignIn(session.user.id), { replace: true });
    } catch (err: unknown) {
      setError(authErrorMessage(err, "The account couldn't be created."));
      setLoading(false);
    }
  };

  return (
    <AuthCardLayout footnote="Closed beta · invite only · paper and live trading on Alpaca">
      <FormHeader
        title="Finish creating your account"
        subtitle={
          ticket
            ? 'Your Alpaca account is connected. Add your details to finish.'
            : 'This page finishes a sign-up that started on Alpaca.'
        }
      />
      {ticket ? (
        <FormNote tone="ok">
          <b>Alpaca account connected.</b> Its keys are stored encrypted.
        </FormNote>
      ) : (
        <FormNote tone="warn">
          This sign-up link is missing its details. Please start again from{' '}
          <Link to="/register" className={LINK}>
            Create an account
          </Link>
          .
        </FormNote>
      )}
      {ticket && (
        <form onSubmit={handleSubmit} className="grid gap-3.5">
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
          <div className="grid grid-cols-2 gap-3">
            <Field
              id="firstName"
              label="First name"
              value={firstName}
              onChange={(e) => setFirstName(e.target.value)}
              autoComplete="given-name"
            />
            <Field
              id="lastName"
              label="Last name"
              value={lastName}
              onChange={(e) => setLastName(e.target.value)}
              autoComplete="family-name"
            />
          </div>
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
      )}
    </AuthCardLayout>
  );
}
