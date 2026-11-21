import { NotificationCategory } from '@llamatrade/core/proto/events_pb';
import { ChannelType } from '@llamatrade/core/proto/notification_pb';
import { router } from 'expo-router';
import { Check, Lock } from 'lucide-react-native';
import { Pressable, View } from 'react-native';

import { cellState, type CellState } from '../../../src/account/notificationModel';
import { CATEGORY_GROUPS, categoryLabel, ROUTING } from '../../../src/account/notifications';
import { usePreferences } from '../../../src/account/usePreferences';
import { makeStyles, radius, useTheme } from '../../../src/theme';
import { Card, Loading, Notice, PanelError, Screen, Text } from '../../../src/ui';

const back = { label: 'Account', onPress: () => (router.canGoBack() ? router.back() : router.replace('/account')) };

const CHANNELS = [
  { key: ChannelType.EMAIL, label: 'Email' },
  { key: ChannelType.WEBHOOK, label: 'Webhook' },
] as const;

function Cell({ state, label, disabled, onToggle }: { state: CellState; label: string; disabled: boolean; onToggle: () => void }) {
  const { c } = useTheme();
  const s = useStyles();
  if (state === 'unavailable') {
    return (
      <View style={s.cell} accessibilityLabel={`${label}, not sent on this channel`}>
        <Text variant="small" tone="fg3">·</Text>
      </View>
    );
  }
  const on = state !== 'off';
  const locked = state === 'locked';
  return (
    <Pressable
      accessibilityRole="checkbox"
      accessibilityLabel={locked ? `${label}, always on` : label}
      accessibilityState={{ checked: on, disabled: locked || disabled }}
      disabled={locked || disabled}
      onPress={onToggle}
      hitSlop={8}
      style={s.cell}
    >
      <View style={[s.box, on ? s.boxOn : null, locked ? s.boxLocked : null]}>
        {on ? (locked ? <Lock color={c.accentInk} size={10} strokeWidth={3} /> : <Check color={c.accentInk} size={12} strokeWidth={3} />) : null}
      </View>
    </Pressable>
  );
}

export default function NotificationsScreen() {
  const s = useStyles();
  const { preferences, load, saving, saveError, toggle, reload } = usePreferences();

  return (
    <Screen title="Notifications" back={back} art="bold" artSeed="account-notifications">
      <Text variant="small" tone="fg2" style={s.intro}>
        Every notice appears in the app. Choose which ones also send an email or reach your webhook, and tap a notice to see the email it sends.
      </Text>
      {load === 'loading' ? <Loading label="Loading your delivery settings" /> : null}
      {load === 'error' ? (
        <PanelError title="Delivery settings couldn't be loaded" detail="Notifications still arrive in the app." onRetry={reload} />
      ) : null}
      {saveError ? <Notice detail={saveError} /> : null}
      {load === 'ready'
        ? CATEGORY_GROUPS.map((group) => (
            <Card key={group.label} style={s.group}>
              <View style={[s.row, s.headRow]}>
                <Text variant="label" tone="fg3" style={s.flex}>{group.label}</Text>
                {CHANNELS.map((ch) => (
                  <Text key={ch.key} variant="label" tone="fg3" style={s.colHead}>{ch.label}</Text>
                ))}
              </View>
              {group.categories.map((cat: NotificationCategory, i) => {
                const label = categoryLabel(cat);
                return (
                  <Pressable
                    key={cat}
                    accessibilityRole="button"
                    accessibilityHint="Shows the email this notice sends"
                    onPress={() => router.push({ pathname: '/account/notifications/[category]', params: { category: String(cat) } })}
                    style={({ pressed }) => [s.row, i < group.categories.length - 1 ? s.divider : null, pressed ? s.pressed : null]}
                  >
                    <Text variant="body" style={s.flex} numberOfLines={1}>{label}</Text>
                    {CHANNELS.map((ch) => (
                      <Cell
                        key={ch.key}
                        state={cellState(ROUTING, preferences, ch.key, cat)}
                        label={`${label} by ${ch.label.toLowerCase()}`}
                        disabled={saving}
                        onToggle={() => toggle(ch.key, cat)}
                      />
                    ))}
                  </Pressable>
                );
              })}
            </Card>
          ))
        : null}
      {load === 'ready' ? (
        <Text variant="caption" tone="fg3">
          A lock means the notice always emails, because it can need a decision from you. A dot means it never goes to that channel.
        </Text>
      ) : null}
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  intro: { marginTop: -6 },
  group: { paddingVertical: 2 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, minHeight: 44 },
  headRow: { minHeight: 34, borderBottomWidth: 1, borderColor: t.c.line },
  colHead: { width: 58, textAlign: 'center' },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  pressed: { opacity: 0.7 },
  cell: { width: 58, alignItems: 'center', justifyContent: 'center', height: 40 },
  box: { width: 20, height: 20, borderRadius: radius.xs, borderWidth: 1.5, borderColor: t.c.lineStrong, alignItems: 'center', justifyContent: 'center' },
  boxOn: { backgroundColor: t.c.accentFill, borderColor: t.c.accentFill },
  boxLocked: { opacity: 0.55 },
}));
