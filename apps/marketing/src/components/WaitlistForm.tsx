import { useEffect, useState } from 'react';

/**
 * WaitlistForm — the "Join the beta" form, ported 1:1 from the static page's
 * Loops.so integration, but as React state instead of DOM manipulation.
 *
 * CONFIGURE before shipping — two equivalent routes:
 *   1. Set the `VITE_LOOPS_FORM_ID` env var at build time (see README), or
 *   2. Replace the `REPLACE_WITH_LOOPS_FORM_ID` fallback literal below.
 * Create a Form in Loops (https://loops.so) to get the id. Until one is set the
 * form validates + shows a "not connected yet" message rather than POSTing. For
 * Kit/ConvertKit instead, point WAITLIST_ENDPOINT at
 * "https://app.kit.com/forms/FORM_ID/subscriptions" and set WAITLIST_FIELD to
 * "email_address".
 *
 * Keeps the honeypot, email regex, localStorage "already joined" flag, and the
 * success state.
 */
const LOOPS_FORM_ID = import.meta.env.VITE_LOOPS_FORM_ID ?? 'REPLACE_WITH_LOOPS_FORM_ID';
const WAITLIST_ENDPOINT = `https://app.loops.so/api/newsletter-form/${LOOPS_FORM_ID}`;
const WAITLIST_FIELD = 'email';
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const STORAGE_KEY = 'lt_waitlist';

interface LoopsResponse {
  success?: boolean;
  message?: string;
}

export function WaitlistForm() {
  const [email, setEmail] = useState('');
  const [company, setCompany] = useState(''); // honeypot
  const [message, setMessage] = useState('');
  const [error, setError] = useState(false);
  const [done, setDone] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    try {
      if (localStorage.getItem(STORAGE_KEY) === '1') setDone(true);
    } catch {
      /* localStorage unavailable — ignore */
    }
  }, []);

  const showDone = (): void => {
    setMessage('');
    setError(false);
    setDone(true);
    try {
      localStorage.setItem(STORAGE_KEY, '1');
    } catch {
      /* ignore */
    }
  };

  const fail = (text: string): void => {
    setMessage(text);
    setError(true);
  };

  const onSubmit = async (e: React.FormEvent<HTMLFormElement>): Promise<void> => {
    e.preventDefault();
    if (company) {
      // honeypot filled → silently "succeed"
      showDone();
      return;
    }
    const value = email.trim();
    if (!EMAIL_RE.test(value)) {
      fail('Enter a valid email address.');
      return;
    }
    if (/REPLACE_WITH_LOOPS_FORM_ID/.test(WAITLIST_ENDPOINT)) {
      fail("Waitlist isn't connected yet — drop in your Loops form ID.");
      return;
    }

    setSubmitting(true);
    const body = new URLSearchParams();
    body.append(WAITLIST_FIELD, value);
    body.append('source', 'landing');
    try {
      const res = await fetch(WAITLIST_ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        body,
      });
      let data: LoopsResponse;
      try {
        data = (await res.json()) as LoopsResponse;
      } catch {
        data = { success: res.ok };
      }
      if (data.success !== false) {
        showDone();
      } else {
        fail(data.message ?? 'Something went wrong — please try again.');
        setSubmitting(false);
      }
    } catch {
      fail('Network error — please try again.');
      setSubmitting(false);
    }
  };

  return (
    <>
      {!done && (
        <form className="wl" onSubmit={onSubmit} noValidate>
          <input
            className="wl-field"
            type="email"
            name="email"
            placeholder="you@email.com"
            autoComplete="email"
            inputMode="email"
            required
            aria-label="Email address"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <input
            className="wl-hp"
            type="text"
            name="company"
            tabIndex={-1}
            autoComplete="off"
            aria-hidden="true"
            value={company}
            onChange={(e) => setCompany(e.target.value)}
          />
          <button className="wl-btn" type="submit" disabled={submitting}>
            {submitting ? (
              'Adding…'
            ) : (
              <>
                Request invite <span className="arr">→</span>
              </>
            )}
          </button>
        </form>
      )}
      <div className={`wl-msg${error ? ' err' : ''}`} role="status" aria-live="polite">
        {message}
      </div>
      {done && (
        <div className="wl-done">
          <span className="o">✓</span> You&apos;re on the list.
        </div>
      )}
      <p className="wl-note">
        No spam — just your invite when a spot opens. We never share your email.
      </p>
    </>
  );
}
