import { Check } from 'lucide-react';
import { useState, type FormEvent } from 'react';

import { INVITE_EMAIL, WAITLIST_AUTH_URL } from '../../config/marketing';
import { useInviteDone } from '../hooks/useInviteDone';
import {
  INVITE_COPY,
  inviteMailto,
  isValidEmail,
  readInviteResponse,
  waitlistBody,
  waitlistEndpoint,
  type WaitlistSource,
} from '../lib/invite';

const ENDPOINT = waitlistEndpoint(WAITLIST_AUTH_URL);
const MAILTO = ENDPOINT ? null : inviteMailto(INVITE_EMAIL);

/** Email field that joins the waitlist. Closed, with a note, when no auth URL is configured. */
export function InviteForm({
  id = 'invite',
  source = 'landing',
}: {
  id?: string;
  source?: WaitlistSource;
}) {
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState('');
  const [message, setMessage] = useState(ENDPOINT ? '' : INVITE_COPY.closed);
  const [done, markDone] = useInviteDone();
  const [sending, setSending] = useState(false);

  const onSubmit = async (e: FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (!ENDPOINT) {
      setMessage(INVITE_COPY.closed);
      return;
    }
    if (!company && !isValidEmail(email)) {
      setMessage(INVITE_COPY.invalid);
      return;
    }
    setSending(true);
    setMessage('');
    try {
      const res = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', 'Connect-Protocol-Version': '1' },
        body: waitlistBody(email, source, company),
      });
      const body: unknown = await res.json().catch(() => null);
      const result = readInviteResponse(res.status, body);
      if (result.ok) {
        markDone();
      } else {
        setMessage(result.message);
      }
    } catch {
      setMessage(INVITE_COPY.network);
    } finally {
      setSending(false);
    }
  };

  if (MAILTO) {
    return (
      <div className="invite-mail">
        <a className="mk-btn pri" href={MAILTO}>
          Email us for an invite
          <i className="arr" aria-hidden="true">
            →
          </i>
        </a>
        <p className="invite-msg note">Places open in small groups. We reply to every request.</p>
      </div>
    );
  }

  if (done) {
    return (
      <div className="invite-ok" role="status">
        <span className="tick" aria-hidden="true">
          <Check size={15} strokeWidth={2.25} />
        </span>
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
        <div className="hp" aria-hidden="true">
          <input
            type="text"
            name="company"
            tabIndex={-1}
            autoComplete="off"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
          />
        </div>
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
