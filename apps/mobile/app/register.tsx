import { router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { StepLine, TextLink } from '../src/account/parts';
import { checkRegister, registerError, type RegisterField } from '../src/auth/errors';
import { AuthShell, FormError, toFailure } from '../src/auth/ui';
import { authClient } from '../src/net/clients';
import { useAuthStore } from '../src/stores/auth';
import { makeStyles } from '../src/theme';
import { Button, Field, Text } from '../src/ui';

/** The path under the example: backtests now, paper and live later (create2 A). */
function PathStrip() {
  const s = useStyles();
  return (
    <View style={s.strip}>
      <View style={s.stripHead}>
        <Text variant="label" tone="fg2" style={s.flex}>Backtest now · paper and live later</Text>
        <Text variant="numSmall" tone="fg3">1 of 3</Text>
      </View>
      <StepLine current={0} />
      <Text variant="caption" tone="fg3">
        Backtests need no broker. Paper needs Alpaca paper, and live is a separate connection when you choose.
      </Text>
    </View>
  );
}

export default function RegisterScreen() {
  const setSession = useAuthStore((s) => s.setSession);
  const params = useLocalSearchParams<{ email?: string; code?: string }>();
  const [workspace, setWorkspace] = useState('');
  const [email, setEmail] = useState(params.email ?? '');
  const [inviteCode, setInviteCode] = useState(params.code ?? '');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [fieldError, setFieldError] = useState<{ field: RegisterField; message: string } | null>(null);
  const [formError, setFormError] = useState<string | null>(null);

  const errorFor = (f: RegisterField) => (fieldError?.field === f ? fieldError.message : null);
  const edit = (f: RegisterField, set: (v: string) => void) => (v: string) => {
    set(v);
    if (fieldError?.field === f) setFieldError(null);
  };

  const submit = async () => {
    setFormError(null);
    const local = checkRegister({ workspace, email, password, inviteCode });
    if (local?.field) {
      setFieldError({ field: local.field, message: local.message });
      return;
    }
    setFieldError(null);
    setBusy(true);
    try {
      await authClient.register({
        tenantName: workspace.trim(),
        email: email.trim(),
        password,
        inviteCode: inviteCode.trim(),
        firstName: '',
        lastName: '',
      });
      // Register returns no tokens, so sign in with the new credentials.
      const res = await authClient.login({ email: email.trim(), password });
      const u = res.user;
      if (!u) throw new Error('Account created, but sign-in returned no user.');
      setSession(
        { id: u.id, email: u.email, firstName: u.firstName, lastName: u.lastName, avatarUrl: u.avatarUrl, tenantId: u.tenantId, roles: u.roles },
        res.accessToken,
        res.refreshToken,
      );
      router.replace('/onboarding');
    } catch (e) {
      const err = registerError(toFailure(e));
      if (err.field) setFieldError({ field: err.field, message: err.message });
      else setFormError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthShell title="Create an account" subtitle="Start building and testing strategies." artSeed="auth-create" top={<PathStrip />}>
      <FormError message={formError} />
      <Field label="Workspace name" value={workspace} onChange={edit('workspace', setWorkspace)} placeholder="Rivera" autoCapitalizeWords textContentType="organizationName" error={errorFor('workspace')} help="Shown at the top of the app. You can change it later." />
      <Field label="Email address" value={email} onChange={edit('email', setEmail)} placeholder="you@example.com" keyboardType="email-address" textContentType="emailAddress" error={errorFor('email')} />
      <Field label="Password" value={password} onChange={edit('password', setPassword)} placeholder="At least 8 characters" secure textContentType="newPassword" error={errorFor('password')} help="At least 8 characters." />
      <Field label="Invite code" value={inviteCode} onChange={edit('inviteCode', setInviteCode)} placeholder="ABCD-EFGH" mono textContentType="oneTimeCode" error={errorFor('inviteCode')} help="From your invite email. Use the address it was sent to." />
      <Button label={busy ? 'Creating account' : 'Create account'} onPress={submit} loading={busy} />
      <View style={s0.row}>
        <Text variant="small" tone="fg2">Have an account?</Text>
        <TextLink label="Sign in" onPress={() => (router.canGoBack() ? router.back() : router.replace('/login'))} />
      </View>
    </AuthShell>
  );
}

const s0 = { row: { flexDirection: 'row', justifyContent: 'center', gap: 5 } } as const;

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  strip: { gap: 10, padding: 12, borderRadius: 12, borderWidth: 1, borderColor: t.c.line, backgroundColor: t.c.panel },
  stripHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
}));
