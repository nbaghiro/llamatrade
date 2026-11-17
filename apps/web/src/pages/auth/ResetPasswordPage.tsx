import { Code, ConnectError } from '@connectrpc/connect';
import { Check, Clock } from 'lucide-react';
import { useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';

import { AuthSplitLayout } from '../../components/auth/AuthSplitLayout';
import { authErrorMessage } from '../../components/auth/errors';
import { Field, FormFoot, FormNote, LINK } from '../../components/auth/fields';
import { ResendLinkForm } from '../../components/auth/ResendLinkForm';
import { Pill } from '../../components/ui';
import { authClient } from '../../services/grpc-client';

const MIN_LENGTH = 8;

type Stage = 'form' | 'saved' | 'expired';

/** The server reports a bad or used token as "Invalid or expired reset link". */
function isExpiredLink(err: unknown): boolean {
  return (
    err instanceof ConnectError &&
    err.code === Code.InvalidArgument &&
    /expired|invalid.*link/i.test(err.rawMessage)
  );
}

function Rule({ met, children }: { met: boolean; children: string }) {
  return (
    <span className={`inline-flex items-center gap-[5px] ${met ? 'text-fg-2' : 'text-fg-3'}`}>
      <Check
        aria-hidden="true"
        className={`h-3.5 w-3.5 ${met ? 'text-accent' : 'text-line-strong'}`}
      />
      {children}
    </span>
  );
}

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get('token') ?? '';
  const [stage, setStage] = useState<Stage>(token ? 'form' : 'expired');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [fieldError, setFieldError] = useState<{ password?: string; confirm?: string }>({});

  const longEnough = password.length >= MIN_LENGTH;
  const matches = password.length > 0 && password === confirm;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!longEnough || !matches) {
      setFieldError(
        longEnough
          ? { confirm: "The two entries don't match. Type the new password again." }
          : { password: `Use at least ${MIN_LENGTH} characters.` }
      );
      return;
    }
    setFieldError({});
    setLoading(true);
    setError('');
    try {
      await authClient.resetPassword({ token, newPassword: password });
      setStage('saved');
    } catch (err) {
      if (isExpiredLink(err)) setStage('expired');
      else setError(authErrorMessage(err, "The password couldn't be saved. Please try again."));
    } finally {
      setLoading(false);
    }
  };

  if (stage === 'expired') {
    return (
      <AuthSplitLayout
        title="This link has expired"
        subtitle="Reset links last one hour and work once. Ask for a new one and use the most recent email."
        status={
          <Pill tone="risk">
            <Clock aria-hidden="true" className="h-3.5 w-3.5" />
            Link expired
          </Pill>
        }
      >
        <ResendLinkForm
          send={(email) => authClient.requestPasswordReset({ email })}
          sentNote={
            <>
              <b>Check your inbox.</b> If that address has an account, a new link is on its way. It
              expires in one hour.
            </>
          }
        />
        <FormFoot>
          <Link to="/login" className={LINK}>
            Back to sign in
          </Link>
        </FormFoot>
      </AuthSplitLayout>
    );
  }

  if (stage === 'saved') {
    return (
      <AuthSplitLayout
        title="Password saved"
        subtitle="Sign in with your new password. Any other signed-in devices have been signed out."
        status={<Pill tone="accent">Saved</Pill>}
      >
        <Link to="/login" className="btn btn-primary btn-lg w-full">
          Sign in
        </Link>
      </AuthSplitLayout>
    );
  }

  return (
    <AuthSplitLayout title="Choose a new password" subtitle="For your LlamaTrade account.">
      <form onSubmit={handleSubmit} className="grid gap-3.5">
        {error && <FormNote tone="warn">{error}</FormNote>}
        <Field
          id="password"
          label="New password"
          type="password"
          value={password}
          onChange={(e) => {
            setPassword(e.target.value);
            setFieldError({});
          }}
          error={fieldError.password}
          autoComplete="new-password"
          required
        />
        <Field
          id="confirm"
          label="Confirm new password"
          type="password"
          value={confirm}
          onChange={(e) => {
            setConfirm(e.target.value);
            setFieldError({});
          }}
          error={fieldError.confirm}
          autoComplete="new-password"
          required
        />
        <div className="flex flex-wrap gap-x-3.5 gap-y-1 text-[12px]">
          <Rule met={longEnough}>{`At least ${MIN_LENGTH} characters`}</Rule>
          <Rule met={matches}>Both entries match</Rule>
        </div>
        <button type="submit" className="btn btn-primary btn-lg w-full" disabled={loading}>
          {loading ? 'Saving…' : 'Save password'}
        </button>
      </form>
    </AuthSplitLayout>
  );
}
