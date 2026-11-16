import { ConnectError } from '@connectrpc/connect';
import { router } from 'expo-router';
import { useState } from 'react';

import { AuthShell, FormError } from '../src/auth/ui';
import { authClient } from '../src/net/clients';
import { useAuthStore } from '../src/stores/auth';
import { Button, Field, Notice } from '../src/ui';

export default function RegisterScreen() {
  const setSession = useAuthStore((s) => s.setSession);
  const [tenantName, setTenantName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    if (!tenantName.trim() || !email.trim() || !password) {
      setError('Fill in every field to continue.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await authClient.register({ tenantName: tenantName.trim(), email: email.trim(), password, firstName: '', lastName: '' });
      // Register returns no tokens, so sign in with the new credentials.
      const res = await authClient.login({ email: email.trim(), password });
      const u = res.user;
      if (!u) throw new Error('Account created, but sign-in returned no user.');
      setSession(
        {
          id: u.id,
          email: u.email,
          firstName: u.firstName,
          lastName: u.lastName,
          avatarUrl: u.avatarUrl,
          tenantId: u.tenantId,
          roles: u.roles,
        },
        res.accessToken,
        res.refreshToken,
      );
      router.replace('/(tabs)');
    } catch (e) {
      setError(
        e instanceof ConnectError ? e.rawMessage || e.message : e instanceof Error ? e.message : 'Registration failed',
      );
    } finally {
      setBusy(false);
    }
  };

  const back = () => (router.canGoBack() ? router.back() : router.replace('/login'));

  return (
    <AuthShell
      title="Create an account"
      subtitle="Start building and testing your strategies."
      back={{ label: 'Sign in', onPress: back }}
    >
      <Notice tone="neutral" detail="LlamaTrade is in a closed beta. Use the email address your invite was sent to." />
      <FormError message={error} />
      <Field label="Company or project name" value={tenantName} onChange={setTenantName} placeholder="Rivera Capital" autoCapitalizeWords />
      <Field label="Email address" value={email} onChange={setEmail} placeholder="you@example.com" keyboardType="email-address" />
      <Field label="Password" value={password} onChange={setPassword} placeholder="At least 8 characters" secure />
      <Button label={busy ? 'Creating account' : 'Create account'} onPress={submit} loading={busy} style={{ marginTop: 4 }} />
    </AuthShell>
  );
}
