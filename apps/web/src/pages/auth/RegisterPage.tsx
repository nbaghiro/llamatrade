import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';

import { AccountPath, AccountPathLine } from '../../components/auth/AccountPath';
import { SIGNUP_PATH } from '../../components/auth/accountPaths';
import { AuthSplitLayout } from '../../components/auth/AuthSplitLayout';
import { registerError, type RegisterField } from '../../components/auth/errors';
import {
  AlpacaButton,
  Field,
  FormFoot,
  FormNote,
  LINK,
  OrDivider,
} from '../../components/auth/fields';
import { rememberInvite } from '../../components/auth/invite';
import { startAuthWithAlpaca } from '../../services/alpacaOAuth';
import { authClient } from '../../services/grpc-client';

export default function RegisterPage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();

  const [inviteCode, setInviteCode] = useState(params.get('code') ?? '');
  const [tenantName, setTenantName] = useState('');
  const [email, setEmail] = useState(params.get('email') ?? '');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [fieldError, setFieldError] = useState<{ field: RegisterField; message: string } | null>(
    null
  );
  const [loading, setLoading] = useState(false);

  const errorFor = (field: RegisterField) =>
    fieldError?.field === field ? fieldError.message : undefined;
  const clear = (field: RegisterField) => {
    if (fieldError?.field === field) setFieldError(null);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setFieldError(null);
    setLoading(true);
    try {
      await authClient.register({ tenantName, email, password, inviteCode: inviteCode.trim() });
      navigate('/login', { state: { registered: true } });
    } catch (err: unknown) {
      const shown = registerError(err);
      if (shown.field) setFieldError({ field: shown.field, message: shown.message });
      else setError(shown.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <AuthSplitLayout
      title="Create an account"
      subtitle="Start building and testing strategies."
      asideFoot={<AccountPath steps={SIGNUP_PATH} />}
      strip={
        <section
          aria-label="Where your account starts"
          className="grid gap-2.5 rounded-panel border border-line bg-panel px-3.5 py-3"
        >
          <div className="flex items-center justify-between gap-2.5 text-[11px] font-medium text-fg-3">
            <span>Backtest now · paper and live later</span>
            <span className="num">1 of 3</span>
          </div>
          <AccountPathLine />
        </section>
      }
    >
      <form onSubmit={handleSubmit} className="grid gap-3.5">
        <FormNote>Accounts are by invite. Use the email address your invite was sent to.</FormNote>
        {error && <FormNote tone="warn">{error}</FormNote>}
        <Field
          id="inviteCode"
          label="Invite code"
          type="text"
          value={inviteCode}
          onChange={(e) => {
            setInviteCode(e.target.value);
            clear('inviteCode');
          }}
          autoComplete="off"
          spellCheck={false}
          autoCapitalize="characters"
          placeholder="ABCD-EFGH"
          help="It's in your invite email."
          error={errorFor('inviteCode')}
          className="num uppercase"
          required
        />
        <Field
          id="tenantName"
          label="Workspace name"
          type="text"
          value={tenantName}
          onChange={(e) => setTenantName(e.target.value)}
          autoComplete="organization"
          help="Shown at the top of the app. You can change it later."
          required
        />
        <Field
          id="email"
          label="Email address"
          type="email"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            clear('email');
          }}
          error={errorFor('email')}
          autoComplete="email"
          required
        />
        <Field
          id="password"
          label="Password"
          help="At least 8 characters, with a letter and a digit."
          type="password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            clear('password');
          }}
          error={errorFor('password')}
          autoComplete="new-password"
          minLength={8}
          required
        />
        <button type="submit" className="btn btn-primary btn-lg w-full" disabled={loading}>
          {loading ? 'Creating account…' : 'Create account'}
        </button>
      </form>
      <OrDivider />
      <AlpacaButton
        label="Sign up with Alpaca"
        onClick={() => {
          rememberInvite(inviteCode);
          startAuthWithAlpaca();
        }}
        disabled={loading}
      />
      <FormFoot>
        Have an account?{' '}
        <Link to="/login" className={LINK}>
          Sign in
        </Link>
      </FormFoot>
    </AuthSplitLayout>
  );
}
