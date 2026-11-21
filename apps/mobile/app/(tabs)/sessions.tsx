import { money, signedMoney } from '@llamatrade/core/format';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { router } from 'expo-router';
import { Plus } from 'lucide-react-native';
import { useMemo } from 'react';
import { Pressable, View } from 'react-native';
import { useShallow } from 'zustand/react/shallow';

import { HeaderActions } from '../../src/shell/HeaderActions';
import { day, fillsBySession, useNeedsYou, useSessionRows } from '../../src/sessions/data';
import { countLine, groupByAccount, laneX, needsLine, rebalanceDays, type FillInput, type SessionGroup, type SessionRow } from '../../src/sessions/model';
import { Lane, ModeTag, NeedsCard } from '../../src/sessions/parts';
import { makeStyles, radius, useTheme } from '../../src/theme';
import { EmptyState, Loading, PanelError, Screen, Text, pnlTone } from '../../src/ui';

const STATE_LABEL: Record<SessionRow['state'], string> = {
  running: 'Running',
  waiting: 'Waiting to start',
  paused: 'Paused',
  frozen: 'Frozen',
  stopped: 'Stopped',
  error: 'Stopped by an error',
};

/** Sessions tab (sessions/phone2 B, list2 A): what needs you, then every session on one timeline. */
export default function SessionsScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const rows = useSessionRows();
  const needs = useNeedsYou(rows);
  const { orders, loading, loaded, error } = useTradingStore(
    useShallow((st) => ({ orders: st.orders, loading: st.loading, loaded: st.loaded, error: st.error })),
  );
  const groups = useMemo(() => groupByAccount(rows), [rows]);

  const now = Date.now();
  const start = useMemo(() => Math.min(now, ...rows.map((r) => r.startedAt ?? now)), [rows, now]);
  const fills = useMemo(() => fillsBySession(orders), [orders]);

  const refresh = () => useTradingStore.getState().loadBlotter().catch(() => undefined);
  const subtitle = needs.length ? needsLine(needs.length) : countLine(rows);

  return (
    <Screen
      title="Sessions"
      tab
      art="bold"
      artSeed="sessions-tab"
      refreshing={loading && loaded}
      onRefresh={refresh}
      right={
        <View style={s.headerRight}>
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Start a session"
            onPress={() => router.push('/sessions/start')}
            hitSlop={6}
            style={[s.plus, { borderColor: c.lineStrong }]}
          >
            <Plus color={c.fg} size={18} strokeWidth={1.8} />
          </Pressable>
          <HeaderActions />
        </View>
      }
    >
      {subtitle ? <Text variant="small" tone="fg2" style={s.subtitle}>{subtitle}</Text> : null}

      <NeedsCard
        items={needs}
        onOpen={(item) =>
          item.kind === 'frozen'
            ? router.push({ pathname: '/sessions/[id]', params: { id: item.target } })
            : router.push({ pathname: '/sessions/order/[id]', params: { id: item.target } })
        }
      />

      {!loaded ? (
        <Loading label="Loading sessions" />
      ) : error && rows.length === 0 ? (
        <PanelError title="Sessions could not be loaded" detail={error} onRetry={refresh} />
      ) : rows.length === 0 ? (
        <EmptyState title="No sessions yet" detail="Start a strategy on paper and it will run here." />
      ) : (
        groups.map((g) => (
          <AccountGroup
            key={g.mode}
            group={g}
            start={start}
            now={now}
            fillsFor={(id) => fills.get(id) ?? []}
          />
        ))
      )}
    </Screen>
  );
}

function AccountGroup({
  group,
  start,
  now,
  fillsFor,
}: {
  group: SessionGroup;
  start: number;
  now: number;
  fillsFor: (sessionId: string) => readonly FillInput[];
}) {
  const s = useStyles();
  const { c } = useTheme();
  const live = group.mode === 'live';
  return (
    <View style={s.group}>
      <View style={s.groupHead}>
        <ModeTag mode={group.mode} />
        <Text variant="small" tone="fg2" style={s.flex} numberOfLines={1}>
          Alpaca {group.mode} · {group.counted === 1 ? '1 session' : `${group.counted} sessions`}
        </Text>
        <Text variant="numStrong">{money(group.total, 2)}</Text>
      </View>
      <View style={[s.card, live ? { borderColor: c.line } : { borderColor: c.lineStrong, borderStyle: 'dashed' }]}>
        {group.rows.map((r, i) => (
          <SessionLaneRow key={r.id} row={r} start={start} now={now} fills={fillsFor(r.id)} first={i === 0} />
        ))}
      </View>
    </View>
  );
}

function SessionLaneRow({
  row,
  start,
  now,
  fills,
  first,
}: {
  row: SessionRow;
  start: number;
  now: number;
  fills: readonly FillInput[];
  first: boolean;
}) {
  const s = useStyles();
  const { c } = useTheme();
  const stopped = row.state === 'stopped';
  const end = stopped && row.endedAt ? row.endedAt : now;
  const days = rebalanceDays(fills);
  const today = new Date().toDateString();
  const todays = days.find((d) => new Date(d.day).toDateString() === today);
  const marks = days.map((d) => ({ x: laneX(d.at, start, now), side: 'buy' as const }));
  const attention = row.state === 'frozen' || row.state === 'error';
  const status = stopped
    ? `Stopped ${day(row.endedAt)} · final value`
    : row.state === 'running' && row.version
      ? `Running · v${row.version}`
      : STATE_LABEL[row.state];
  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => router.push({ pathname: '/sessions/[id]', params: { id: row.id } })}
      style={({ pressed }) => [s.row, first ? null : { borderTopWidth: 1, borderColor: c.line }, pressed ? { opacity: 0.7 } : null]}
    >
      <View style={s.rowTop}>
        <Text variant="subhead" tone={stopped ? 'fg3' : 'fg'} style={s.flex} numberOfLines={1}>{row.title}</Text>
        <Text variant="num" tone={stopped ? 'fg3' : 'fg'}>{row.value !== null ? money(row.value, 2) : '–'}</Text>
      </View>
      <Lane
        from={row.startedAt ? laneX(row.startedAt, start, now) : 0}
        to={laneX(end, start, now)}
        marks={marks}
        stopped={stopped}
        attention={attention}
        muted={stopped}
        badge={todays ? todays.fills.length : undefined}
        now
      />
      <View style={s.rowTop}>
        <Text variant="small" tone={attention ? 'risk' : 'fg3'} style={s.flex} numberOfLines={1}>{status}</Text>
        {row.today !== null ? (
          <Text variant="numSmall" tone={pnlTone(row.today)}>
            {signedMoney(row.today, 2)} today
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1, minWidth: 0 },
  headerRight: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  plus: { width: 34, height: 34, borderRadius: 17, borderWidth: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: t.c.panel },
  subtitle: { marginTop: -8 },
  group: { gap: 8 },
  groupHead: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingHorizontal: 2 },
  card: { backgroundColor: t.c.panel, borderWidth: 1, borderRadius: radius.lg, paddingHorizontal: 16 },
  row: { paddingVertical: 13, gap: 6 },
  rowTop: { flexDirection: 'row', alignItems: 'center', gap: 10 },
}));
