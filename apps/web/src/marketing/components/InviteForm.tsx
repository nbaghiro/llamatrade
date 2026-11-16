import { useEffect, useState, type FormEvent } from 'react';

import { LOOPS_FORM_ID } from '../../config/marketing';
import {
  INVITE_COPY,
  INVITE_DONE_KEY,
  inviteBody,
  inviteEndpoint,
  isValidEmail,
  readInviteResponse,
} from '../lib/invite';

const ENDPOINT = inviteEndpoint(LOOPS_FORM_ID);

function rememberDone(): void {
  try {
    localStorage.setItem(INVITE_DONE_KEY, '1');
  } catch {
    /* storage unavailable: the confirmation still shows for this visit */
  }
}

/** Email field that posts to the Loops form. Closed, with a note, when no form id is set. */
export function InviteForm({ id = 'invite' }: { id?: string }) {
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [message, setMessage] = useState(ENDPOINT ? '' : INVITE_COPY.closed);
  const [done, setDone] = useState(false);
  const [sending, setSending] = useState(false);

  useEffect(() => {
    try {
      if (localStorage.getItem(INVITE_DONE_KEY) === '1') setDone(true);
    } catch {
      /* storage unavailable */
    }
  }, []);

  const finish = () => {
    setMessage('');
    setDone(true);
    rememberDone();
  };

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (company) {
      finish();
      return;
    }
    if (!ENDPOINT) {
      setMessage(INVITE_COPY.closed);
      return;
    }
    if (!isValidEmail(email)) {
      setMessage(INVITE_COPY.invalid);
      return;
    }
    setSending(true);
    setMessage('');
    try {
      const res = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body: inviteBody(email),
      });
      const body: unknown = await res.json().catch(() => null);
      const result = readInviteResponse(res.status, body);
      if (result.ok) finish();
      else setMessage(result.message);
    } catch {
      setMessage(INVITE_COPY.network);
    } finally {
      setSending(false);
    }
  };

  if (done) {
    return (
      <div className="invite-ok" role="status">
        {INVITE_COPY.done}
      </div>
    );
  }

  return (
    <>
      <form className="invite" id={id} onSubmit={onSubmit} noValidate>
        <input
          type="email"
          name="email"
          placeholder="you@example.com"
          aria-label="Email address"
          autoComplete="email"
          inputMode="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={!ENDPOINT}
          aria-describedby={`${id}-msg`}
        />
        <input
          className="hp"
          type="text"
          name="company"
          tabIndex={-1}
          autoComplete="off"
          aria-hidden="true"
          value={company}
          onChange={(e) => setCompany(e.target.value)}
        />
        <button className="mk-btn pri" type="submit" disabled={!ENDPOINT || sending}>
          {sending ? 'Sending…' : 'Request an invite'}
          {!sending && (
            <i className="arr" aria-hidden="true">
              →
            </i>
          )}
        </button>
      </form>
      <div
        id={`${id}-msg`}
        className={`invite-msg ${ENDPOINT ? '' : 'note'}`}
        role="status"
        aria-live="polite"
      >
        {message}
      </div>
    </>
  );
}
