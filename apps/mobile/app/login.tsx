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
      if (!u) throw new Error('Login succeeded but returned no user.');
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
    <SafeAreaView style={{ flex: 1, backgroundColor: palette.bone }}>
      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={{ flexGrow: 1, justifyContent: 'center', padding: 22, gap: 14 }} keyboardShouldPersistTaps="handled">
          <AuthBrand />

          <Display size={30} style={{ marginTop: 8 }}>Sign In</Display>
          <Label style={{ marginTop: -8 }}>Welcome back — access your account</Label>

          {error ? (
            <View style={{ borderWidth: 2, borderColor: palette.red[500], backgroundColor: palette.red[50], padding: 10 }}>
              <Mono size={11} color={palette.red[600]}>{error}</Mono>
            </View>
          ) : null}

          <Field label="Email address" value={email} onChange={setEmail} placeholder="you@example.com" />
          <Field label="Password" value={password} onChange={setPassword} placeholder="••••••••" secure />

          <Pressable
            onPress={signIn}
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
            <Mono size={12} style={{ fontWeight: '700' }}>{busy ? 'SIGNING IN…' : 'SIGN IN'}</Mono>
          </Pressable>

          <SocialAuth />

          <View style={{ flexDirection: 'row', justifyContent: 'center', alignItems: 'center', gap: 5, marginTop: 4 }}>
            <Body size={11} color={palette.gray[500]}>New to LlamaTrade?</Body>
            <Pressable onPress={() => router.push('/register')} hitSlop={8}>
              <Mono size={11} color={palette.orange[500]} style={{ fontWeight: '700' }}>SIGN UP</Mono>
            </Pressable>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}
