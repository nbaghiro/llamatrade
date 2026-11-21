import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { router } from 'expo-router';
import { useEffect, useMemo } from 'react';
import { Pressable, View } from 'react-native';

import { Lanes, type Lane } from '../src/charts/Lanes';
import { laneCode } from '../src/charts/scale';
import { useHomeData } from '../src/home/data';
import { attentionItems, fillsOn, sessionRows, type Attention } from '../src/home/model';
import { dayLabel, hm } from '../src/home/when';
import { makeStyles, radius } from '../src/theme';
import { Card, EmptyState, Screen, Text } from '../src/ui';

const back = { label: 'Back', onPress: () => (router.canGoBack() ? router.back() : router.replace('/')) };

/** Today's market hours, 09:30 to 16:00 local, for the lanes. */
function marketDay(now: number): { from: number; until: number } {
  const open = new Date(now);
  open.setHours(9, 30, 0, 0);
  const close = new Date(now);
  close.setHours(16, 0, 0, 0);
  return { from: open.getTime(), until: close.getTime() };
}

/** Notifications (shell/notifications2 A): today as lanes per session, what needs you, then earlier. */
export default function NotificationsScreen() {
  const s = useStyles();
  const d = useHomeData();
  const { notifications, fetchNotifications, markAsRead } = useNotificationsStore();

  useEffect(() => {
    fetchNotifications();
  }, [fetchNotifications]);

  const rows = useMemo(() => sessionRows(d.sessions).filter((r) => r.state !== 'stopped'), [d.sessions]);
  const today = useMemo(() => fillsOn(d.fills, d.now), [d.fills, d.now]);
  const needs = useMemo(() => attentionItems(d.frozen, d.rejected), [d.frozen, d.rejected]);
  const day = marketDay(d.now);
  const lanes: Lane[] = rows.map((r) => {
    const mine = today.filter((f) => (r.sessionId ? f.sessionId === r.sessionId : f.strategyId === r.strategyId));
    const byMinute = new Map<number, number>();
    for (const f of mine) {
      const m = Math.floor(f.t / 60_000) * 60_000;
      byMinute.set(m, (byMinute.get(m) ?? 0) + 1);
    }
    const attention = r.state === 'frozen' || r.state === 'error';
    return {
      key: r.id,
      label: laneCode(r.title),
      tone: attention ? 'risk' : r.mode === 'live' ? 'ink' : 'accent',
      dashed: r.mode === 'paper' && !attention,
      start: attention ? day.from : undefined,
      end: attention ? Math.min(d.now, day.until) : undefined,
      markers: [...byMinute.entries()].map(([t, count]) => ({ t, kind: 'fill' as const, count, id: String(t) })),
    };
  });
  const earlier = notifications.slice(0, 30);
  const open = (a: Attention) => {
    if (a.kind === 'frozen') {
      const x = d.sessions.find((y) => y.id === a.executionId);
      if (x?.sessionId) router.push({ pathname: '/sessions/[id]', params: { id: x.sessionId } });
    } else router.push({ pathname: '/sessions/order/[id]', params: { id: a.orderId } });
  };

  return (
    <Screen title="Notifications" art="bold" artSeed="shell-notifications-today" back={back} refreshing={d.refreshing} onRefresh={d.refresh}>
      {lanes.length ? (
        <Card style={s.lanes}>
          <Text variant="label" tone="fg3">
            TODAY · {today.length === 0 ? 'NO FILLS YET' : today.length === 1 ? '1 FILL' : `${today.length} FILLS`}
          </Text>
          <View style={s.laneBox}>
            <Lanes lanes={lanes} from={day.from} until={day.until} now={Math.min(d.now, day.until)} labelWidth={28} />
          </View>
          <View style={s.ticks}>
            <Text variant="numSmall" tone="fg3" style={s.tick}>
              09:30
            </Text>
            <Text variant="numSmall" tone="fg3" style={s.tick}>
              16:00
            </Text>
          </View>
        </Card>
      ) : null}

      {needs.length ? (
        <>
          <Text variant="subhead">Needs you</Text>
          {needs.map((a) => (
            <Card key={a.key} style={s.need} onPress={() => open(a)}>
              <View style={s.needHead}>
                <Text variant="bodyStrong" style={s.flex}>
                  {a.title}
                </Text>
                {a.kind === 'rejected' && a.t ? (
                  <Text variant="numSmall" tone="fg3">
                    {hm(a.t)}
                  </Text>
                ) : null}
              </View>
              <Text variant="small" tone="fg2">
                {a.detail}
              </Text>
              <View style={s.needAction}>
                <Text variant="small" tone="risk">
                  {a.kind === 'frozen' ? 'Review the difference' : 'Review the order'}
                </Text>
              </View>
            </Card>
          ))}
        </>
      ) : null}

      <Text variant="subhead">Earlier</Text>
      {earlier.length === 0 ? (
        <EmptyState title="No notifications" detail="Fills, rebalances and anything that needs you are listed here." />
      ) : (
        <Card style={s.list}>
          {earlier.map((n, i) => {
            const t = n.createdAt?.seconds ? Number(n.createdAt.seconds) * 1000 : null;
            return (
              <Pressable
                key={n.id}
                onPress={() => (n.isRead ? undefined : markAsRead(n.id))}
                style={[s.row, i < earlier.length - 1 ? s.divider : null]}
              >
                <Text variant="numSmall" tone="fg3" style={s.when}>
                  {t ? (dayLabel(t, d.now) === 'Today' ? hm(t) : dayLabel(t, d.now)) : ''}
                </Text>
                <View style={s.flex}>
                  <Text variant={n.isRead ? 'small' : 'smallStrong'}>{n.title}</Text>
                  {n.message ? (
                    <Text variant="caption" tone="fg3" numberOfLines={2}>
                      {n.message}
                    </Text>
                  ) : null}
                </View>
                {!n.isRead ? <View style={s.unread} /> : null}
              </Pressable>
            );
          })}
        </Card>
      )}
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  lanes: { gap: 8, paddingVertical: 12 },
  laneBox: { marginTop: 2 },
  ticks: { flexDirection: 'row', justifyContent: 'space-between', paddingLeft: 28 },
  tick: { fontSize: 10.5 },
  need: { gap: 6, borderColor: t.c.riskLine },
  needHead: { flexDirection: 'row', alignItems: 'baseline', gap: 10 },
  needAction: {
    alignSelf: 'flex-start',
    marginTop: 4,
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: t.c.riskLine,
    backgroundColor: t.c.riskSoft,
  },
  list: { paddingVertical: 2 },
  row: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingVertical: 11 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  when: { width: 64, marginTop: 1 },
  unread: { width: 7, height: 7, borderRadius: 4, backgroundColor: t.c.accent, marginTop: 6 },
}));
