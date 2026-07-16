import { ConnectError } from '@connectrpc/connect';
import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { AuthBrand, Field, SocialAuth } from '../src/auth/ui';
import { authClient } from '../src/net/clients';
import { useAuthStore } from '../src/stores/auth';
import { palette } from '../src/theme';
import { Body, Display, Label, Mono } from '../src/ui';

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
      // Register returns no tokens — sign in immediately with the new credentials.
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

  return (
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bone }}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', padding: 22, gap: 14 }} keyboardShouldPersistTaps="handled">
          <AuthBrand />

          <Display size={30} style={{ marginTop: 8 }}>Create Account</Display>
          <Label style={{ marginTop: -8 }}>Start building your trading strategies</Label>

          {error ? (
            <View style={{ borderWidth: 2, borderColor: palette.red[500], backgroundColor: palette.red[50], padding: 10 }}>
              <Mono size={11} color={palette.red[600]}>{error}</Mono>
            </View>
          ) : null}

          <Field label="Company / Project name" value={tenantName} onChange={setTenantName} placeholder="Acme Capital" autoCapitalizeWords />
          <Field label="Email address" value={email} onChange={setEmail} placeholder="you@example.com" />
          <Field label="Password" value={password} onChange={setPassword} placeholder="At least 8 characters" secure />

          <Pressable
            onPress={submit}
            disabled={busy}
            style={{
              backgroundColor: busy ? palette.orange[300] : palette.orange[500],
              borderWidth: 2,
              borderColor: palette.ink,
              paddingVertical: 13,
              alignItems: 'center',
              flexDirection: 'row',
              justifyContent: 'center',
              gap: 8,
            }}
          >
            {busy ? <ActivityIndicator size="small" color={palette.ink} /> : null}
            <Mono size={12} style={{ fontWeight: '700' }}>{busy ? 'CREATING…' : 'CREATE ACCOUNT'}</Mono>
          </Pressable>

          <SocialAuth />

          <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 5, marginTop: 4 }}>
            <Body size={11} color={palette.gray[500]}>Already have an account?</Body>
            <Pressable onPress={() => (router.canGoBack() ? router.back() : router.replace('/login'))} hitSlop={8}>
              <Mono size={11} color={palette.orange[500]} style={{ fontWeight: '700' }}>SIGN IN</Mono>
            </Pressable>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
