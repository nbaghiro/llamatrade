import { ConnectError } from '@connectrpc/connect';
import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { AuthShell, FormError } from '../src/auth/ui';
import { authClient } from '../src/net/clients';
import { useAuthStore } from '../src/stores/auth';
import { Button, Field, Text } from '../src/ui';

const PREFILL_EMAIL = 'demo@llamatrade.ai';
const PREFILL_PASSWORD = 'demo1234';

export default function LoginScreen() {
  const setSession = useAuthStore((s) => s.setSession);
  const [email, setEmail] = useState(PREFILL_EMAIL);
  const [password, setPassword] = useState(PREFILL_PASSWORD);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const signIn = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await authClient.login({ email: email.trim(), password });
      const u = res.user;
      if (!u) throw new Error('Sign-in succeeded but returned no user.');
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
        e instanceof ConnectError ? e.rawMessage || e.message : e instanceof Error ? e.message : 'Sign in failed',
      );
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Sign in" subtitle="Welcome back. Sign in to your account.">
      <FormError message={error} />
      <Field label="Email address" value={email} onChange={setEmail} placeholder="you@example.com" keyboardType="email-address" />
      <Field label="Password" value={password} onChange={setPassword} placeholder="Your password" secure />
      <Button label={busy ? 'Signing in' : 'Sign in'} onPress={signIn} loading={busy} style={{ marginTop: 4 }} />
      <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 5, marginTop: 6 }}>
        <Text variant="small" tone="fg2">New to LlamaTrade?</Text>
        <Text variant="small" tone="accent" onPress={() => router.push('/register')}>
          Create an account
        </Text>
      </View>
    </AuthShell>
  );
}
