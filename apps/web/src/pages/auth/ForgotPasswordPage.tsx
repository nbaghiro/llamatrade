import { Check } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';

import { AuthSplitLayout } from '../../components/auth/AuthSplitLayout';
import { Field, FormFoot, FormNote, LINK } from '../../components/auth/fields';
import { authClient } from '../../services/grpc-client';

type SendState = 'idle' | 'sending' | 'sent';

export default function ForgotPasswordPage() {
  const [email, setEmail] = useState('');
  const [state, setState] = useState<SendState>('idle');
  const [sentTo, setSentTo] = useState('');
  const [failed, setFailed] = useState(false);

  const send = async () => {
    setState('sending');
    setFailed(false);
    try {
      await authClient.requestPasswordReset({ email });
      setSentTo(email);
      setState('sent');
    } catch {
      setFailed(true);
      setState(sentTo ? 'sent' : 'idle');
    }
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    send().catch(() => undefined);
  };

  // Editing the address after sending makes the button usable again.
  const sent = state === 'sent' && email === sentTo;

  return (
    <AuthSplitLayout
      title="Reset your password"
      subtitle="We'll email you a link to choose a new one."
    >
      <form onSubmit={handleSubmit} className="grid gap-3.5">
        <Field
          id="email"
          label="Email address"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
        />
        {sent ? (
          <button type="button" className="btn btn-secondary btn-lg w-full" disabled>
            <Check aria-hidden="true" className="h-4 w-4" />
            Link sent
          </button>
        ) : (
          <button
            type="submit"
            className="btn btn-primary btn-lg w-full"
            disabled={state === 'sending'}
          >
            {state === 'sending' ? 'Sending…' : 'Send reset link'}
          </button>
        )}
        {failed && (
          <FormNote tone="warn">
            The link couldn&apos;t be sent just now. Please try again.
          </FormNote>
        )}
        {sent && !failed && (
          <FormNote tone="ok">
            <b>Check your inbox.</b> If that address has an account, a reset link is on its way. It
            expires in one hour.{' '}
            <button type="button" className={LINK} onClick={() => send().catch(() => undefined)}>
              Send again
            </button>
          </FormNote>
        )}
      </form>
      <FormFoot>
        Remembered it?{' '}
        <Link to="/login" className={LINK}>
          Sign in
        </Link>
      </FormFoot>
    </AuthSplitLayout>
  );
}
