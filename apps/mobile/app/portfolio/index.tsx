import { money, signedMoney } from '@llamatrade/core/format';
import { router } from 'expo-router';
import { ChevronRight, Plus } from 'lucide-react-native';
import { useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';

import { AnnotatedCurve } from '../../src/charts/AnnotatedCurve';
import { Lanes } from '../../src/charts/Lanes';
import { SplitBar } from '../../src/charts/SplitBar';
import { useHomeData } from '../../src/home/data';
import { toChartLanes } from '../../src/home/laneView';
import { accountSplit, blendEquity, sessionLanes, sessionRows, type Mode, type Point, type SessionRow } from '../../src/home/model';
import { OfflineStrip } from '../../src/home/OfflineStrip';
import { PaperAmount } from '../../src/home/PaperAmount';
import { DayChange, ModeSwatch } from '../../src/home/parts';
import { shortDate } from '../../src/home/when';
import { makeStyles, radius, useTheme } from '../../src/theme';
import { Card, Loading, Notice, PanelError, Screen, Text, pnlTone } from '../../src/ui';

const LABEL_W = 28;
type Account = 'both' | Mode;

/** Portfolio (overview2 A money in, accounts2 C split that filters). Pushed from Home. */
export default function PortfolioScreen() {
  const { c } = useTheme();
  const s = useStyles();
  const d = useHomeData();
  const [account, setAccount] = useState<Account>('both');

  const split = useMemo(() => accountSplit(d.sessions, d.paperCash, d.liveCash), [d.sessions, d.paperCash, d.liveCash]);
  const shown = useMemo(() => d.sessions.filter((x) => account === 'both' || x.mode === account), [d.sessions, account]);
  const rows = useMemo(() => sessionRows(shown), [shown]);
  const curve = useMemo(() => blendEquity(shown.map((x) => x.equity)), [shown]);
  const added = useMemo(() => moneyIntoSessions(shown), [shown]);
  const lanes = useMemo(() => toChartLanes(sessionLanes(shown, d.fills, []), { moneyIn: true }), [shown, d.fills]);
  const from = Math.min(curve[0]?.t ?? d.now, added[0]?.t ?? d.now);
  const toggle = (a: Mode) => setAccount((cur) => (cur === a ? 'both' : a));
  const cash = account === 'live' ? d.liveCash : account === 'paper' ? d.paperCash : null;

  return (
    <Screen
      title="Portfolio"
      artSeed="portfolio-money-in"
      art="bold"
      back={{ label: 'Home', onPress: () => (router.canGoBack() ? router.back() : router.replace('/')) }}
      right={
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Add paper funds"
          onPress={() => router.push('/portfolio/add-funds')}
          hitSlop={8}
          style={s.plus}
        >
          <Plus color={c.fg} size={18} strokeWidth={1.8} />
        </Pressable>
      }
      refreshing={d.refreshing}
      onRefresh={d.refresh}
    >
      <OfflineStrip />
      {d.loading ? (
        <Loading label="Loading portfolio" />
      ) : d.error && !d.loaded ? (
        <PanelError title="Couldn't load the portfolio" detail={d.error} onRetry={d.refresh} />
      ) : (
        <>
          {d.error ? <Notice title="Couldn't refresh." detail={`${d.error} Pull down to try again.`} /> : null}
          <View style={s.hero}>
            <Text variant="label" tone="fg3">
              TOTAL EQUITY
            </Text>
            <Text variant="hero">{money(d.totalEquity, 2)}</Text>
            <DayChange amount={d.dayPnl} percent={d.dayPnlPercent} suffix="today" />
          </View>

          <View style={s.accounts}>
            {(['live', 'paper'] as const).map((m) => {
              const mine = d.sessions.filter((x) => x.mode === m && x.state !== 'stopped');
              const total = m === 'live' ? split.live : split.paper;
              const selected = account === m;
              return (
                <Pressable
                  key={m}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  onPress={() => toggle(m)}
                  style={[s.account, m === 'paper' ? s.accountPaper : null, selected ? s.accountOn : null, account !== 'both' && !selected ? s.dim : null]}
                >
                  <View style={[s.modeTag, m === 'live' ? s.modeTagLive : null]}>
                    <Text variant="numSmall" style={[s.modeTagText, m === 'live' ? s.modeTagTextLive : null]}>
                      {m === 'live' ? 'LIVE' : 'PAPER'}
                    </Text>
                  </View>
                  <PaperAmount paper={m === 'paper'} variant="numStrong">
                    {money(total, 2)}
                  </PaperAmount>
                  <SplitBar
                    height={6}
                    segments={[
                      ...mine.map((x) => ({ key: x.id, value: x.value ?? 0, look: m === 'live' ? ('solid' as const) : ('hatched' as const) })),
                      { key: 'cash', value: (m === 'live' ? d.liveCash : d.paperCash) ?? 0, look: 'muted' as const },
                    ]}
                  />
                </Pressable>
              );
            })}
          </View>

          {curve.length > 1 ? (
            <View style={s.chart}>
              <AnnotatedCurve
                series={curve}
                step={added}
                from={from}
                until={d.now}
                inset={LABEL_W}
                height={150}
                accessibilityLabel="Sessions' value over time, over a dashed line of money added to them"
              />
              {lanes.length ? <Lanes lanes={lanes} from={from} until={d.now} labelWidth={LABEL_W} onPressLane={(l) => openRow(rows.find((r) => r.id === l.key))} /> : null}
              <View style={s.legend}>
                <View style={s.legendItem}>
                  <View style={s.diamond} />
                  <Text variant="caption" tone="fg3">
                    Money in
                  </Text>
                </View>
                <View style={s.legendItem}>
                  <View style={s.dash} />
                  <Text variant="caption" tone="fg3">
                    Money added to sessions
                  </Text>
                </View>
              </View>
            </View>
          ) : null}

          <Card style={s.list}>
            {rows.map((r, i) => (
              <StatementRow key={r.id} row={r} last={i === rows.length - 1 && cash === null && account !== 'both'} onPress={() => openRow(r)} />
            ))}
            {account === 'both' || cash !== null ? (
              <CashRows liveCash={account === 'paper' ? null : d.liveCash} paperCash={account === 'live' ? null : d.paperCash} />
            ) : null}
          </Card>

          <Card style={s.list}>
            <LinkRow label="Activity" detail="Every fill, transfer and dividend" onPress={() => router.push('/portfolio/activity')} />
            <LinkRow label="Checks against Alpaca" detail="Whether the ledger matches each account" onPress={() => router.push('/portfolio/checks')} />
            <LinkRow label="Add paper funds" detail="Then choose where they go" onPress={() => router.push('/portfolio/add-funds')} last />
          </Card>
        </>
      )}
    </Screen>
  );

  function openRow(r: SessionRow | undefined) {
    if (!r) return;
    if (r.sleeveId) router.push({ pathname: '/portfolio/sleeve/[id]', params: { id: r.sleeveId } });
    else if (r.sessionId) router.push({ pathname: '/sessions/[id]', params: { id: r.sessionId } });
  }
}

/** Each session's allocation as a step on the day it started, oldest first. */
function moneyIntoSessions(sessions: readonly { startedAt: number | null; allocated: number }[]): Point[] {
  let sum = 0;
  return sessions
    .filter((x) => x.startedAt !== null && x.allocated > 0)
    .sort((a, b) => (a.startedAt ?? 0) - (b.startedAt ?? 0))
    .map((x) => {
      sum += x.allocated;
      return { t: x.startedAt ?? 0, v: sum };
    });
}

function StatementRow({ row, last, onPress }: { row: SessionRow; last: boolean; onPress: () => void }) {
  const s = useStyles();
  const gain = row.value !== null ? row.value - row.allocated : null;
  const stopped = row.state === 'stopped';
  const sub = [
    row.mode === 'live' ? 'Live' : 'Paper',
    stopped ? `stopped${row.endedAt ? ` ${shortDate(row.endedAt)}` : ''}` : row.state === 'frozen' ? 'frozen' : null,
    row.allocated > 0 ? `added ${money(row.allocated)}` : null,
  ]
    .filter(Boolean)
    .join(' · ');
  return (
    <Pressable onPress={onPress} style={({ pressed }) => [s.row, last ? null : s.divider, pressed ? s.pressed : null]}>
      <ModeSwatch mode={row.mode} />
      <View style={s.flex}>
        <Text variant="body" tone={stopped ? 'fg2' : 'fg'} numberOfLines={1}>
          {row.title}
        </Text>
        <Text variant="small" tone={row.state === 'frozen' ? 'risk' : 'fg3'} numberOfLines={1}>
          {sub}
        </Text>
      </View>
      <View style={s.figures}>
        <PaperAmount paper={row.mode === 'paper'} variant="numStrong" tone={stopped ? 'fg2' : 'fg'}>
          {row.value !== null ? money(row.value, 2) : 'No value'}
        </PaperAmount>
        {gain !== null && row.allocated > 0 ? (
          <Text variant="numSmall" tone={pnlTone(gain)}>
            {signedMoney(gain, 2)}
          </Text>
        ) : null}
      </View>
    </Pressable>
  );
}

function CashRows({ liveCash, paperCash }: { liveCash: number | null; paperCash: number | null }) {
  const s = useStyles();
  const rows = [
    liveCash !== null ? { key: 'live', label: 'Live cash, unallocated', v: liveCash, paper: false } : null,
    paperCash !== null ? { key: 'paper', label: 'Paper cash, unallocated', v: paperCash, paper: true } : null,
  ].filter((r): r is { key: string; label: string; v: number; paper: boolean } => r !== null);
  return (
    <>
      {rows.map((r, i) => (
        <View key={r.key} style={[s.row, i < rows.length - 1 ? s.divider : null]}>
          <View style={s.cashSwatch} />
          <Text variant="body" tone="fg2" style={s.flex}>
            {r.label}
          </Text>
          <PaperAmount paper={r.paper} variant="numStrong" tone="fg2">
            {money(r.v, 2)}
          </PaperAmount>
        </View>
      ))}
    </>
  );
}

function LinkRow({ label, detail, onPress, last = false }: { label: string; detail: string; onPress: () => void; last?: boolean }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <Pressable onPress={onPress} accessibilityRole="link" style={({ pressed }) => [s.row, last ? null : s.divider, pressed ? s.pressed : null]}>
      <View style={s.flex}>
        <Text variant="body">{label}</Text>
        <Text variant="small" tone="fg3">
          {detail}
        </Text>
      </View>
      <ChevronRight color={c.fg3} size={16} strokeWidth={1.8} />
    </Pressable>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1, minWidth: 0 },
  dim: { opacity: 0.5 },
  pressed: { opacity: 0.7 },
  plus: {
    width: 34,
    height: 34,
    borderRadius: 17,
    alignItems: 'center',
    justifyContent: 'center',
    borderWidth: 1,
    borderColor: t.c.lineStrong,
    backgroundColor: t.c.panel,
  },
  hero: { gap: 4 },
  accounts: { flexDirection: 'row', gap: 10 },
  account: {
    flex: 1,
    gap: 10,
    padding: 12,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: t.c.line,
    backgroundColor: t.c.panel,
  },
  accountPaper: { borderStyle: 'dashed', borderColor: t.c.lineStrong },
  accountOn: { borderColor: t.c.fg, borderStyle: 'solid', borderWidth: 1.5 },
  modeTag: { alignSelf: 'flex-start', borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.pill, paddingHorizontal: 7, paddingVertical: 1 },
  modeTagLive: { backgroundColor: t.c.fg, borderColor: t.c.fg },
  modeTagText: { fontSize: 10, lineHeight: 14, color: t.c.fg2, letterSpacing: 0.4 },
  modeTagTextLive: { color: t.c.canvas },
  chart: { gap: 8, padding: 8, marginHorizontal: -8, borderRadius: 12, backgroundColor: t.c.canvas + "b3" },
  legend: { flexDirection: 'row', gap: 16, justifyContent: 'center' },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  diamond: { width: 7, height: 7, backgroundColor: t.c.accent, transform: [{ rotate: '45deg' }] },
  dash: { width: 16, height: 0, borderTopWidth: 1.5, borderColor: t.c.fg2, borderStyle: 'dashed' },
  list: { paddingVertical: 2 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 12 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  figures: { alignItems: 'flex-end', gap: 2 },
  cashSwatch: { width: 10, height: 10, borderRadius: 2, backgroundColor: t.c.lineStrong },
}));
