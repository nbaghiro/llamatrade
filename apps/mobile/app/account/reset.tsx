import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { TextLink } from '../../src/account/parts';
import { checkSignIn, isUnreachable, resetError, UNREACHABLE, type ResetState } from '../../src/auth/errors';
import { AuthShell, FormError, toFailure } from '../../src/auth/ui';
import { authClient } from '../../src/net/clients';
import { Button, Field, Text } from '../../src/ui';

const LINK_RULE = 'Reset links last one hour and work once.';

const COPY: Record<ResetState, { title: string; subtitle: string }> = {
  request: { title: 'Reset your password', subtitle: `Enter the email you sign in with and we'll send a link. ${LINK_RULE}` },
  sent: { title: 'Check your email', subtitle: `If an account uses that address, a reset link is on its way. ${LINK_RULE}` },
  choose: { title: 'Choose a new password', subtitle: 'Use at least 8 characters. You stay signed out until you sign in with it.' },
  expired: { title: 'This link has expired', subtitle: `${LINK_RULE} Ask for a new one and use the most recent email.` },
  done: { title: 'Password changed', subtitle: 'Sign in with your new password.' },
};

const goSignIn = () => router.replace('/login');

export default function ResetScreen() {
  const params = useLocalSearchParams<{ email?: string; token?: string }>();
  const token = params.token ?? '';
  const [state, setState] = useState<ResetState>(token ? 'choose' : 'request');
  const [email, setEmail] = useState(params.email ?? '');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const sendLink = async () => {
    setFormError(null);
    const local = checkSignIn(email, 'x');
    if (local) {
      setFieldError(local.message);
      return;
    }
    setFieldError(null);
    setBusy(true);
    try {
      await authClient.requestPasswordReset({ email: email.trim() });
      setState('sent');
    } catch (e) {
      const f = toFailure(e);
      setFormError(isUnreachable(f) ? UNREACHABLE : f.message || "The link couldn't be sent. Please try again.");
    } finally {
      setBusy(false);
    }
  };

  const savePassword = async () => {
    setFormError(null);
    if (password.length < 8) {
      setFieldError('Use at least 8 characters.');
      return;
    }
    setFieldError(null);
    setBusy(true);
    try {
      await authClient.resetPassword({ token, newPassword: password });
      setState('done');
    } catch (e) {
      const err = resetError(toFailure(e));
      setState(err.state);
      if (err.message) setFieldError(err.message);
    } finally {
      setBusy(false);
    }
  };

  const copy = COPY[state];
  const emailField = (
    <Field
      label="Email address"
      value={email}
      onChange={(v) => {
        setEmail(v);
        setFieldError(null);
      }}
      placeholder="you@example.com"
      keyboardType="email-address"
      textContentType="emailAddress"
      error={fieldError}
    />
  );

  return (
    <AuthShell title={copy.title} subtitle={copy.subtitle} artSeed={`auth-reset-${state}`}>
      <FormError message={formError} />
      {state === 'request' || state === 'expired' ? (
        <>
          {emailField}
          <Button label={state === 'expired' ? 'Send a new link' : 'Send a reset link'} onPress={sendLink} loading={busy} />
        </>
      ) : null}
      {state === 'sent' ? (
        <>
          <Text variant="small" tone="fg2">
            Sent to <Text variant="smallStrong">{email.trim()}</Text>. Open the link on this phone to choose a new password.
          </Text>
          <Button label="Back to sign in" onPress={goSignIn} />
          <TextLink label="Send another link" align="center" onPress={() => setState('request')} />
        </>
      ) : null}
      {state === 'choose' ? (
        <>
          <Field label="New password" value={password} onChange={(v) => { setPassword(v); setFieldError(null); }} placeholder="At least 8 characters" secure textContentType="newPassword" error={fieldError} />
          <Button label="Save the new password" onPress={savePassword} loading={busy} />
        </>
      ) : null}
      {state === 'done' ? <Button label="Sign in" onPress={goSignIn} /> : null}
      {state !== 'sent' && state !== 'done' ? (
        <View style={{ alignItems: 'center' }}>
          <TextLink label="Back to sign in" onPress={goSignIn} />
        </View>
      ) : null}
    </AuthShell>
  );
}
