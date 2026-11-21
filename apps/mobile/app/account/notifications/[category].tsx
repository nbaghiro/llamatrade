import type { NotificationCategory } from '@llamatrade/core/proto/events_pb';
import { ChannelType } from '@llamatrade/core/proto/notification_pb';
import { router, useLocalSearchParams } from 'expo-router';
import { Send } from 'lucide-react-native';
import { Switch, View } from 'react-native';

import { cellState, type CellState } from '../../../src/account/notificationModel';
import { categoryLabel, emailPreview, ROUTING } from '../../../src/account/notifications';
import { usePreferences } from '../../../src/account/usePreferences';
import { useAuthStore } from '../../../src/stores/auth';
import { makeStyles, useTheme } from '../../../src/theme';
import { Button, Card, LogoMark, Notice, Screen, SectionLabel, Text } from '../../../src/ui';

const back = { label: 'Notifications', onPress: () => (router.canGoBack() ? router.back() : router.replace('/account/notifications')) };

function ChannelRow({ label, state, disabled, onToggle, last = false }: { label: string; state: CellState; disabled: boolean; onToggle: () => void; last?: boolean }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <View style={[s.row, last ? null : s.divider]}>
      <Text variant="body" style={s.flex}>{label}</Text>
      {state === 'unavailable' ? (
        <Text variant="small" tone="fg3">Not sent here</Text>
      ) : state === 'locked' ? (
        <Text variant="small" tone="fg3">Always</Text>
      ) : (
        <Switch
          accessibilityLabel={label}
          value={state === 'on'}
          disabled={disabled}
          onValueChange={onToggle}
          trackColor={{ true: c.accentFill, false: c.sunk }}
          thumbColor="#ffffff"
          ios_backgroundColor={c.sunk}
        />
      )}
    </View>
  );
}

export default function NoticeScreen() {
  const s = useStyles();
  const params = useLocalSearchParams<{ category: string }>();
  const category = Number(params.category) as NotificationCategory;
  const email = useAuthStore((st) => st.user?.email ?? '');
  const { preferences, load, saving, saveError, toggle } = usePreferences();
  const label = categoryLabel(category);
  const preview = emailPreview(category);
  const emailState = cellState(ROUTING, preferences, ChannelType.EMAIL, category);
  const webhookState = cellState(ROUTING, preferences, ChannelType.WEBHOOK, category);
  const sendsEmail = emailState === 'on' || emailState === 'locked';

  return (
    <Screen title={label} back={back} art="bold" artSeed={`account-notice-${category}`}>
      {saveError ? <Notice detail={saveError} /> : null}
      <Card style={s.rows}>
        <ChannelRow label="In the app" state="locked" disabled onToggle={() => undefined} />
        <ChannelRow label="Email" state={load === 'ready' ? emailState : 'unavailable'} disabled={saving || load !== 'ready'} onToggle={() => toggle(ChannelType.EMAIL, category)} />
        <ChannelRow label="Webhook" state={load === 'ready' ? webhookState : 'unavailable'} disabled={saving || load !== 'ready'} onToggle={() => toggle(ChannelType.WEBHOOK, category)} last />
      </Card>

      <SectionLabel>What the email says</SectionLabel>
      <Card style={s.email}>
        <Text variant="caption" tone="fg3" numberOfLines={1}>From LlamaTrade{email ? ` · to ${email}` : ''}</Text>
        <Text variant="bodyStrong">{preview.subject}</Text>
        <View style={s.rule} />
        <LogoMark size={22} />
        <Text variant="small" tone="fg2">{preview.body}</Text>
        <Text variant="caption" tone="fg3">
          {emailState === 'unavailable'
            ? `${label} only appears in the app, so no email is sent.`
            : sendsEmail
              ? `You get this because ${label} is on for email.`
              : `${label} is off for email, so this only appears in the app.`}
        </Text>
      </Card>

      <Button label="Send a test" variant="secondary" icon={<Send size={16} strokeWidth={1.8} color={s.icon.color} />} onPress={() => undefined} disabled />
      <Text variant="caption" tone="fg3" style={s.center}>
        An example with made-up figures; the real notice fills in your own. Test emails aren&apos;t available yet.
      </Text>
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  rows: { paddingVertical: 0 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, minHeight: 50 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  email: { gap: 8 },
  rule: { height: 1, backgroundColor: t.c.line, marginVertical: 2 },
  icon: { color: t.c.fg },
  center: { textAlign: 'center' },
}));
