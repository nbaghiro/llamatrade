import { money, num, signedMoney, toDate } from '@llamatrade/core/format';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { router, useLocalSearchParams } from 'expo-router';
import { MoreHorizontal } from 'lucide-react-native';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';
import { useShallow } from 'zustand/react/shallow';

import { LineChart } from '../../../src/charts/LineChart';
import { timeLabels } from '../../../src/charts/paths';
import { clock, day, dayOrToday, fillsOf, sessionRow } from '../../../src/sessions/data';
import { formatQty, symbolLanes, weightPct, type SessionRow } from '../../../src/sessions/model';
import { LabelledLane, ModeTag } from '../../../src/sessions/parts';
import { InkButton, QuietButton, Sheet } from '../../../src/sessions/Sheet';
import { makeStyles, radius, useTheme } from '../../../src/theme';
import { Card, ListRow, Loading, Notice, PanelError, Screen, StatusMark, Text, pnlTone, type RunState } from '../../../src/ui';
import { cadence } from '../../../src/ui/status';

const back = { label: 'Sessions', onPress: () => (router.canGoBack() ? router.back() : router.replace('/sessions')) };

const RUN_STATE: Record<SessionRow['state'], RunState> = {
  running: 'running',
  waiting: 'waiting',
  paused: 'paused',
  frozen: 'frozen',
  stopped: 'stopped',
  error: 'error',
};

/** One session (sessions/detail2 A, frozen2 A, stop2 A): its curve with symbol lanes, then what's next. */
export default function SessionScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { detail, detailLoading, detailError, loadSession, runCommand, commandPending, commandError, sessions, performance } = useTradingStore(
    useShallow((st) => ({
      detail: st.detail,
      detailLoading: st.detailLoading,
      detailError: st.detailError,
      loadSession: st.loadSession,
      runCommand: st.runCommand,
      commandPending: st.commandPending,
      commandError: st.commandError,
      sessions: st.sessions,
      performance: st.performance,
    })),
  );
  const strategies = useStrategiesStore((st) => st.strategies);
  const [menu, setMenu] = useState(false);
  const [stopping, setStopping] = useState(false);

  const listed = sessions.find((x) => x.id === id);
  const startedAt = toDate(listed?.startedAt ?? detail?.session.startedAt);

  useEffect(() => {
    if (!id) return;
    const since = startedAt ?? new Date(Date.now() - 365 * 86_400_000);
    loadSession(id, since).catch(() => undefined);
    if (useStrategiesStore.getState().strategies.length === 0) useStrategiesStore.getState().fetchStrategies().catch(() => undefined);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const current = detail && detail.session.id === id ? detail : null;
  const row = useMemo(
    () =>
      current
        ? sessionRow(current.session, current.execution ? [current.execution] : [], current.sleeve ? [current.sleeve] : [], performance.length ? performance : current.performance ? [current.performance] : [])
        : null,
    [current, performance],
  );

  if (!row || !current) {
    return (
      <Screen title={listed ? listed.name.replace(/\s*\((paper|live)\)$/i, '') : 'Session'} back={back} art="bold" artSeed={`session-${id}`}>
        {detailError ? (
          <PanelError title="This session could not be loaded" detail={detailError} onRetry={() => id && loadSession(id, startedAt ?? new Date(0))} />
        ) : (
          <Loading label="Loading session" />
        )}
      </Screen>
    );
  }

  const stopped = row.state === 'stopped';
  const frozen = row.state === 'frozen';
  const values = current.curve.map((p) => num(p.equity));
  const times = current.curve.map((p) => Number(p.timestamp?.seconds ?? 0));
  const startMs = times.length ? times[0] * 1000 : row.startedAt ?? Date.now();
  const endMs = stopped && row.endedAt ? row.endedAt : Date.now();
  const sinceStart = values.length > 1 && values[0] > 0 ? (values[values.length - 1] / values[0] - 1) * 100 : row.returnAllPct;
  const fills = fillsOf(current.orders.filter((o) => o.sessionId === row.id));
  const heldSymbols = [...current.positions].sort((a, b) => num(b.marketValue) - num(a.marketValue)).map((p) => p.symbol);
  const lanes = symbolLanes(fills, startMs, endMs, heldSymbols).slice(0, 5);
  const recent = [...fills].sort((a, b) => b.at - a.at).slice(0, 3);
  const totalHeld = current.positions.reduce((a, p) => a + num(p.marketValue), 0);
  const strategy = strategies.find((x) => x.id === row.strategyId);
  const every = strategy ? cadence(strategy.rebalance) : '';
  const cash = current.sleeve ? num(current.sleeve.cash?.balance) : null;

  const stop = async () => {
    const ok = await runCommand(row.id, 'stop');
    if (ok) {
      setStopping(false);
      useTradingStore.getState().loadBlotter().catch(() => undefined);
      loadSession(row.id, startedAt ?? new Date(startMs)).catch(() => undefined);
    }
  };
  const pauseOrResume = async (cmd: 'pause' | 'resume') => {
    setStopping(false);
    setMenu(false);
    const ok = await runCommand(row.id, cmd);
    if (ok) useTradingStore.getState().loadBlotter().catch(() => undefined);
  };

  return (
    <Screen
      title={row.title}
      back={back}
      art="bold"
      artSeed={`session-${row.id}`}
      eyebrow={
        <View style={s.eyebrow}>
          <ModeTag mode={row.mode} />
          <StatusMark state={RUN_STATE[row.state]} label={stopped && row.endedAt ? `Stopped ${day(row.endedAt)}` : undefined} />
          {row.version ? <Text variant="small" tone="fg3">v{row.version}</Text> : null}
        </View>
      }
      right={
        stopped ? undefined : (
          <Pressable accessibilityRole="button" accessibilityLabel="More" hitSlop={10} onPress={() => setMenu(true)}>
            <MoreHorizontal color={c.fg2} size={22} strokeWidth={1.8} />
          </Pressable>
        )
      }
      refreshing={detailLoading}
      onRefresh={() => loadSession(row.id, startedAt ?? new Date(startMs))}
    >
      <View style={s.valueBlock}>
        <View style={s.valueRow}>
          <Text variant="hero">{row.value !== null ? money(row.value, 2) : '–'}</Text>
          {row.today !== null ? (
            <Text variant="num" tone={pnlTone(row.today)}>
              {signedMoney(row.today, 2)} <Text variant="small" tone="fg3">today</Text>
            </Text>
          ) : null}
        </View>
        {sinceStart !== null && Number.isFinite(sinceStart) ? (
          <Text variant="small" tone="fg3">
            {stopped ? 'Final value. ' : ''}
            <Text variant="small" tone={pnlTone(sinceStart)}>{`${sinceStart >= 0 ? '+' : '−'}${Math.abs(sinceStart).toFixed(1)}%`}</Text>
            {` since ${day(startMs)}`}
          </Text>
        ) : null}
      </View>

      {frozen ? (
        <Notice
          title={`${row.title} is frozen.`}
          detail="Trading is on hold. The share counts behind the freeze aren't available to the app yet, so it can't be resolved here."
        />
      ) : null}
      {row.state === 'error' ? <Notice title="This session stopped because of an error." detail="Its holdings stay in the sleeve." /> : null}
      {commandError ? <Notice title="That didn't go through." detail={commandError} /> : null}

      <Card style={s.chartCard}>
        {values.length > 1 ? (
          <LineChart values={values} height={170} color={frozen ? c.risk : undefined} />
        ) : (
          <View style={s.noCurve}>
            <Text variant="small" tone="fg3">The curve appears after the first day's equity is recorded.</Text>
          </View>
        )}
        <View style={s.lanes}>
          {frozen ? <LabelledLane label="Session" from={0} to={1} attention /> : null}
          {lanes.map((l) => (
            <LabelledLane key={l.symbol} label={l.symbol} marks={l.marks} to={1} sided muted={stopped} />
          ))}
        </View>
        {times.length > 1 ? (
          <View style={s.axis}>
            <Text variant="numSmall" tone="fg3">{timeLabels(times, 2)[0]}</Text>
            <Text variant="numSmall" tone="fg3">{stopped ? day(endMs) : 'Today'}</Text>
          </View>
        ) : null}
        {lanes.length ? <Text variant="caption" tone="fg3" style={s.legend}>Filled dots are buys, open dots are sells.</Text> : null}
      </Card>

      {!stopped ? (
        <>
          <View style={s.sectionHead}>
            <Text variant="subhead">Next</Text>
            <Text variant="small" tone="accent" onPress={() => router.push({ pathname: '/sessions/[id]/rebalances', params: { id: row.id } })}>
              Rebalances
            </Text>
          </View>
          <Card style={s.list}>
            <ListRow
              label={every ? `${every} rebalance` : 'Rebalance schedule'}
              sub="The next date isn't in the app yet."
              last={row.mode === 'live' || row.state !== 'running'}
            />
            {row.mode === 'paper' && row.state === 'running' ? (
              <ListRow
                last
                label="Run on live"
                sub="Start a live session from this paper record"
                onPress={() => router.push({ pathname: '/sessions/[id]/live', params: { id: row.id } })}
              />
            ) : null}
          </Card>
        </>
      ) : null}

      {current.positions.length ? (
        <>
          <Text variant="subhead" style={s.section}>Holdings</Text>
          <Card style={s.list}>
            {[...current.positions]
              .sort((a, b) => num(b.marketValue) - num(a.marketValue))
              .map((p, i, all) => (
                <ListRow
                  key={p.id || p.symbol}
                  last={i === all.length - 1}
                  onPress={() => router.push({ pathname: '/markets/[symbol]', params: { symbol: p.symbol } })}
                  label={<Text variant="numStrong">{p.symbol}</Text>}
                  sub={`${formatQty(num(p.quantity))} shares${totalHeld > 0 ? ` · ${weightPct(num(p.marketValue) / totalHeld)} of holdings` : ''}`}
                  value={<Text variant="num">{money(p.marketValue, 2)}</Text>}
                />
              ))}
          </Card>
        </>
      ) : null}

      {recent.length ? (
        <>
          <Text variant="subhead" style={s.section}>Recent fills</Text>
          <Card style={s.list}>
            {recent.map((f, i) => (
              <ListRow
                key={f.id}
                last={i === recent.length - 1}
                label={
                  <View style={s.fill}>
                    <Text variant="numSmall" tone="fg3" style={s.side}>{f.side === 'buy' ? 'BUY' : 'SELL'}</Text>
                    <Text variant="body" numberOfLines={1}>{`${formatQty(f.quantity)} ${f.symbol} at $${f.price.toFixed(2)}`}</Text>
                  </View>
                }
                sub={`${dayOrToday(f.at)}, ${clock(f.at)}`}
                value={<Text variant="num">{money(f.quantity * f.price, 2)}</Text>}
              />
            ))}
          </Card>
        </>
      ) : null}

      <Sheet open={menu} onClose={() => setMenu(false)}>
        <Text variant="heading">{row.title}</Text>
        <Card style={s.list}>
          <ListRow label="Rebalances" onPress={() => { setMenu(false); router.push({ pathname: '/sessions/[id]/rebalances', params: { id: row.id } }); }} />
          {row.state === 'paused' ? (
            <ListRow label="Resume" onPress={() => pauseOrResume('resume')} />
          ) : (
            <ListRow label="Pause" sub="Rebalances wait; holdings stay" onPress={() => pauseOrResume('pause')} />
          )}
          <ListRow last label={<Text variant="body" tone="loss">Stop</Text>} onPress={() => { setMenu(false); setStopping(true); }} />
        </Card>
      </Sheet>

      <Sheet open={stopping} onClose={() => setStopping(false)}>
        <View>
          <Text variant="heading">Stop {row.title}?</Text>
          <Text variant="small" tone="fg2">The sleeve closes. Nothing is sold.</Text>
        </View>
        <Card style={s.list}>
          {current.positions.map((p) => (
            <ListRow
              key={p.id || p.symbol}
              label={
                <View style={s.fill}>
                  <Text variant="numStrong" style={s.side}>{p.symbol}</Text>
                  <Text variant="small" tone="fg3">{`${formatQty(num(p.quantity))} · ${money(p.marketValue, 2)}`}</Text>
                </View>
              }
              value={<Text variant="small">Unmanaged</Text>}
            />
          ))}
          <ListRow
            last
            label={
              <View style={s.fill}>
                <Text variant="small" tone="fg2" style={s.side}>Cash</Text>
                <Text variant="small" tone="fg3">{cash !== null ? money(cash, 2) : 'Whatever is left'}</Text>
              </View>
            }
            value={<Text variant="small">Unallocated</Text>}
          />
        </Card>
        <Text variant="small" tone="fg2">
          Holdings stay in Alpaca {row.mode} with no strategy trading them, and no more rebalances run. This can't be undone.
        </Text>
        <InkButton label={`Stop ${row.title}`} onPress={stop} loading={commandPending === 'stop'} />
        {row.state !== 'paused' ? <QuietButton label="Pause instead" onPress={() => pauseOrResume('pause')} /> : null}
      </Sheet>
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  eyebrow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  valueBlock: { gap: 2, marginTop: -4 },
  valueRow: { flexDirection: 'row', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' },
  chartCard: { borderRadius: radius.lg, paddingHorizontal: 12 },
  noCurve: { height: 120, alignItems: 'center', justifyContent: 'center' },
  lanes: { marginTop: 6 },
  axis: { flexDirection: 'row', justifyContent: 'space-between', marginTop: 6, paddingLeft: 52 },
  legend: { marginTop: 4 },
  sectionHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 8, marginBottom: -4 },
  section: { marginTop: 8, marginBottom: -4 },
  list: { paddingVertical: 2, borderRadius: radius.lg },
  fill: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  side: { width: 40 },
}));
