import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { TextLink } from '../src/account/parts';
import { checkSignIn, signInError, type SignInField } from '../src/auth/errors';
import { AuthShell, ExampleStrip, FormError, toFailure } from '../src/auth/ui';
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
  const [fieldError, setFieldError] = useState<{ field: SignInField; message: string } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const errorFor = (f: SignInField) => (fieldError?.field === f ? fieldError.message : null);

  const signIn = async () => {
    setFormError(null);
    const local = checkSignIn(email, password);
    if (local?.field) {
      setFieldError({ field: local.field, message: local.message });
      return;
    }
    setFieldError(null);
    setBusy(true);
    try {
      const res = await authClient.login({ email: email.trim(), password });
      const u = res.user;
      if (!u) throw new Error('Sign-in succeeded but returned no user.');
      setSession(
        { id: u.id, email: u.email, firstName: u.firstName, lastName: u.lastName, avatarUrl: u.avatarUrl, tenantId: u.tenantId, roles: u.roles },
        res.accessToken,
        res.refreshToken,
      );
      router.replace('/(tabs)');
    } catch (e) {
      const err = signInError(toFailure(e));
      if (err.field) setFieldError({ field: err.field, message: err.message });
      else setFormError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Sign in" subtitle="Welcome back to LlamaTrade." artSeed="auth-sign-in" top={<ExampleStrip />}>
      <FormError message={formError} />
      <Field
        label="Email address"
        value={email}
        onChange={(v) => {
          setEmail(v);
          if (fieldError?.field === 'email') setFieldError(null);
        }}
        placeholder="you@example.com"
        keyboardType="email-address"
        textContentType="emailAddress"
        error={errorFor('email')}
      />
      <View style={{ gap: 8 }}>
        <Field
          label="Password"
          value={password}
          onChange={(v) => {
            setPassword(v);
            if (fieldError?.field === 'password') setFieldError(null);
          }}
          placeholder="Your password"
          secure
          textContentType="password"
          error={errorFor('password')}
        />
        <TextLink
          label="Forgot password?"
          align="right"
          onPress={() => router.push({ pathname: '/account/reset', params: { email: email.trim() } })}
        />
      </View>
      <Button label={busy ? 'Signing in' : 'Sign in'} onPress={signIn} loading={busy} />
      <View style={{ flexDirection: 'row', justifyContent: 'center', gap: 5 }}>
        <Text variant="small" tone="fg2">Have an invite?</Text>
        <TextLink label="Create an account" onPress={() => router.push('/register')} />
      </View>
    </AuthShell>
  );
}
