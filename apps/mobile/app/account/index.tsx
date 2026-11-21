import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { router } from 'expo-router';
import { AlertTriangle, Bell, CheckCircle2, ChevronRight, CreditCard, Link2, Lock, ShieldCheck, SunMoon, type LucideIcon } from 'lucide-react-native';
import { useState, type ReactNode } from 'react';
import { Alert, Pressable, View } from 'react-native';

import { etTime } from '../../src/account/health';
import { AlpacaBadge, StateText } from '../../src/account/parts';
import { useAccountSummary, type SectionState } from '../../src/account/useAccountSummary';
import { authClient } from '../../src/net/clients';
import { initials } from '../../src/shell/tabs';
import { useAuthStore } from '../../src/stores/auth';
import { makeStyles, useTheme } from '../../src/theme';
import { Button, Card, Pill, Screen, SectionLabel, Text } from '../../src/ui';

const back = { label: 'Back', onPress: () => (router.canGoBack() ? router.back() : router.replace('/')) };

function Row({
  icon: Icon,
  label,
  state,
  onPress,
  last = false,
  right,
}: {
  icon?: LucideIcon;
  label: string;
  state?: SectionState | null;
  onPress?: () => void;
  last?: boolean;
  right?: ReactNode;
}) {
  const { c } = useTheme();
  const s = useStyles();
  const body = (
    <>
      {Icon ? <Icon color={c.fg3} size={18} strokeWidth={1.7} /> : null}
      <Text variant="body" style={s.flex} numberOfLines={1}>
        {label}
      </Text>
      {right ?? (state ? <StateText label={state.text} risk={state.risk} /> : null)}
      {onPress ? <ChevronRight color={c.fg3} size={16} strokeWidth={1.8} /> : null}
    </>
  );
  const style = [s.row, last ? null : s.divider];
  if (!onPress) return <View style={style}>{body}</View>;
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [style, pressed ? s.pressed : null]}>
      {body}
    </Pressable>
  );
}

export default function AccountScreen() {
  const { c } = useTheme();
  const s = useStyles();
  const user = useAuthStore((st) => st.user);
  const logout = useAuthStore((st) => st.logout);
  const credentials = useBrokerStore((st) => st.credentials);
  const lastCheck = useBrokerStore((st) => st.lastCheck);
  const fetchBroker = useBrokerStore((st) => st.fetch);
  const summary = useAccountSummary();
  const [sending, setSending] = useState(false);

  const name = user ? `${user.firstName ?? ''} ${user.lastName ?? ''}`.trim() || user.email : '';
  const { health, summary: card } = summary;
  const toBroker = () => router.push('/account/broker');

  const sendReset = async () => {
    if (!user?.email) return;
    setSending(true);
    try {
      await authClient.requestPasswordReset({ email: user.email });
      Alert.alert('Reset link sent', `A link is on its way to ${user.email}. It lasts one hour and works once.`);
    } catch {
      Alert.alert("The link couldn't be sent", 'Check your connection and try again.');
    } finally {
      setSending(false);
    }
  };

  const confirmSignOut = () =>
    Alert.alert('Sign out', 'Running sessions keep trading on their schedule while you are signed out.', [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Sign out', style: 'destructive', onPress: logout },
    ]);

  return (
    <Screen title="Account" back={back} art="bold" artSeed="account-home" onRefresh={() => fetchBroker()} refreshing={false}>
      {summary.brokerLoaded ? (
        card.tone === 'risk' ? (
          <Card style={[s.health, s.healthRisk]}>
            <View style={s.healthHead}>
              <AlertTriangle color={c.risk} size={18} strokeWidth={1.8} />
              <Text variant="subhead" style={s.flex}>{card.title}</Text>
            </View>
            <Text variant="small" tone="fg2">{card.body}</Text>
            <Button label="Fix the keys" onPress={toBroker} size="sm" />
          </Card>
        ) : (
          <Card style={s.health} onPress={card.tone === 'none' ? () => router.push('/account/connect-broker') : toBroker}>
            <View style={s.healthHead}>
              {card.tone === 'ok' ? <CheckCircle2 color={c.accent} size={18} strokeWidth={1.8} /> : <Link2 color={c.fg3} size={18} strokeWidth={1.8} />}
              <Text variant="subhead" style={s.flex}>{card.title}</Text>
              <ChevronRight color={c.fg3} size={16} strokeWidth={1.8} />
            </View>
            <Text variant="small" tone="fg2">{card.body}</Text>
          </Card>
        )
      ) : null}

      <Card style={s.profile}>
        <View style={s.avatar}>
          <Text variant="subhead" tone="accent">{initials(user)}</Text>
        </View>
        <View style={s.flex}>
          <Text variant="bodyStrong" numberOfLines={1}>{name}</Text>
          <Text variant="small" tone="fg3" numberOfLines={1}>{user?.email ?? ''}</Text>
        </View>
      </Card>

      <SectionLabel>Alpaca accounts</SectionLabel>
      <Card style={s.list}>
        {(['live', 'paper'] as const).map((kind, i) => {
          const cred = credentials.find((cr) => (kind === 'paper') === cr.isPaper);
          const problem = health.problems.find((p) => p.kind === kind);
          const running = summary.sessions.filter((se) => se.kind === kind && se.running).length;
          const checked = lastCheck && (kind === 'paper') === lastCheck.isPaper ? etTime(lastCheck.at) : null;
          return (
            <Pressable key={kind} accessibilityRole="button" onPress={cred ? toBroker : () => router.push({ pathname: '/account/connect-broker', params: { env: kind } })} style={({ pressed }) => [s.conn, i === 0 ? s.divider : null, pressed ? s.pressed : null]}>
              <View style={s.connHead}>
                <AlpacaBadge size={20} faded={!cred} />
                <Pill label={kind === 'live' ? 'Live' : 'Paper'} tone={kind === 'live' ? 'accent' : 'neutral'} />
                {cred ? <Text variant="numSmall" tone="fg3">{cred.accountNumber ? `••${cred.accountNumber.slice(-4)}` : `${cred.apiKeyPrefix}••`}</Text> : null}
                <View style={s.flex} />
                <StateText label={!cred ? 'Not connected' : problem ? (problem.reason === 'rejected' ? 'Keys rejected' : 'Keys off') : 'Connected'} risk={!!problem} />
              </View>
              <Text variant="caption" tone="fg3">
                {cred
                  ? `${running === 1 ? '1 session running' : `${running} sessions running`}${checked ? ` · checked ${checked}` : ''}`
                  : kind === 'live'
                    ? 'Real money. Connect it when you want a live session.'
                    : 'Needed for paper sessions. Backtests run without it.'}
              </Text>
            </Pressable>
          );
        })}
      </Card>

      <Card style={s.list}>
        <Row icon={Link2} label="Broker" state={summary.broker} onPress={toBroker} />
        <Row icon={Bell} label="Notifications" state={summary.notifications} onPress={() => router.push('/account/notifications')} />
        <Row icon={SunMoon} label="Appearance" state={summary.appearance} onPress={() => router.push('/account/appearance')} />
        <Row icon={CreditCard} label="Plan and usage" state={summary.plan} onPress={() => router.push('/account/plans')} last />
      </Card>

      <Card style={s.list}>
        <Row icon={Lock} label="Password" right={<Text variant="small" tone="accent">{sending ? 'Sending' : 'Send reset link'}</Text>} onPress={sending ? undefined : sendReset} />
        <Row icon={ShieldCheck} label="Two-factor sign-in" right={<StateText label="Later" />} last />
      </Card>

      <Card style={s.list}>
        <Row label="Sign out" onPress={confirmSignOut} last right={<View />} />
      </Card>
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  health: { gap: 8 },
  healthRisk: { borderColor: t.c.riskLine },
  healthHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  profile: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: t.c.accentSoft,
  },
  list: { paddingVertical: 0 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 48, paddingVertical: 10 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  pressed: { opacity: 0.7 },
  conn: { gap: 6, paddingVertical: 12 },
  connHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
}));
