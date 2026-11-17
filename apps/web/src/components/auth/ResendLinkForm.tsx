import { useState, type FormEvent, type ReactNode } from 'react';

import { useAuthStore } from '../../store/auth';

import { Field, FormNote } from './fields';

type SendState = 'idle' | 'sending' | 'sent' | 'failed';

/** An email field and one button that asks for a fresh link: a reset or a confirmation. */
export function ResendLinkForm({
  send,
  sentNote,
}: {
  send: (email: string) => Promise<unknown>;
  sentNote: ReactNode;
}) {
  const [email, setEmail] = useState(useAuthStore.getState().user?.email ?? '');
  const [state, setState] = useState<SendState>('idle');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    setState('sending');
    send(email)
      .then(() => setState('sent'))
      .catch(() => setState('failed'));
  };

  return (
    <form onSubmit={handleSubmit} className="grid gap-3.5">
      <Field
        id="email"
        label="Email address"
        type="email"
        value={email}
        onChange={(e) => {
          setEmail(e.target.value);
          if (state !== 'sending') setState('idle');
        }}
        autoComplete="email"
        required
      />
      <button
        type="submit"
        className="btn btn-primary btn-lg w-full"
        disabled={state === 'sending' || state === 'sent'}
      >
        {state === 'sending' ? 'Sending…' : state === 'sent' ? 'Link sent' : 'Send a new link'}
      </button>
      {state === 'sent' && <FormNote tone="ok">{sentNote}</FormNote>}
      {state === 'failed' && (
        <FormNote tone="warn">The link couldn&apos;t be sent just now. Please try again.</FormNote>
      )}
    </form>
  );
}
