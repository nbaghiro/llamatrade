import { money, num, pct, signedMoney } from '@llamatrade/core/format';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo } from 'react';
import { View } from 'react-native';

import { AxisLabels, Curve, LineKey, MarkLane } from '../../src/backtests/charts';
import { pointsOf } from '../../src/backtests/data';
import { readStrategy } from '../../src/builder/sentences';
import { SentenceView } from '../../src/builder/SentenceView';
import { fillsOf } from '../../src/sessions/data';
import { rebalanceDays } from '../../src/sessions/model';
import { sessionFacts, useSameDates, useSessionsWithCurves } from '../../src/strategies/data';
import { gapLabel, shortDate, stageLine, stageOf } from '../../src/strategies/model';
import { ModeTag } from '../../src/strategies/parts';
import { makeStyles } from '../../src/theme';
import { Button, Card, ListRow, Loading, PanelError, Screen, StatusMark, Text, pnlTone, type RunState } from '../../src/ui';
import { cadence } from '../../src/ui/status';

const back = { label: 'Strategies', onPress: () => (router.canGoBack() ? router.back() : router.replace('/strategies')) };
const thisYear = new Date().getUTCFullYear();

export default function StrategyOverviewScreen() {
  const s = useStyles();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { strategies, details, detailLoading, runs, runLoading, backtestReturns, fetchStrategyDetail, fetchStrategyRun, fetchStrategies, fetchBacktestReturns } =
    useStrategiesStore();
  const { rows, curves } = useSessionsWithCurves();
  const orders = useTradingStore((st) => st.orders);
  const positions = useTradingStore((st) => st.positions);

  useEffect(() => {
    if (!id) return;
    fetchStrategyDetail(id);
    fetchStrategyRun(id);
    const st = useStrategiesStore.getState();
    if (!st.strategies.length) fetchStrategies();
    if (!Object.keys(st.backtestReturns).length) fetchBacktestReturns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const strategy = (id ? details[id] : undefined) ?? strategies.find((x) => x.id === id);
  const session = rows.find((r) => r.strategyId === id && r.state !== 'stopped') ?? null;
  const points = session?.executionId ? curves[session.executionId] ?? [] : [];
  const same = useSameDates(id ?? '', points, session?.startedAt ?? null, session?.version ?? null);
  const read = useMemo(() => (strategy?.dslCode ? readStrategy(strategy.dslCode) : null), [strategy?.dslCode]);

  if (!strategy || !id) {
    return (
      <Screen title="Strategy" back={back} art="bold" artSeed={`strategy-${id ?? ''}`}>
        {id && detailLoading[id] !== false ? (
          <Loading label="Loading strategy" />
        ) : (
          <PanelError title="This strategy could not be found" detail="It may have been archived or removed." onRetry={id ? () => fetchStrategyDetail(id) : undefined} />
        )}
      </Screen>
    );
  }

  const stage = stageOf(id, sessionFacts(rows), backtestReturns[id] !== undefined || !!runs[id]);
  const runState: RunState = session ? session.state : stage.kind === 'stopped' ? 'stopped' : 'draft';
  const statusLabel = session
    ? `${session.state === 'running' ? 'Running' : session.state.charAt(0).toUpperCase() + session.state.slice(1)} in ${session.mode}`
    : stageLine(stage, thisYear);

  const ready = same.status === 'ready' ? same.same : null;
  const sessionPct = ready ? ready.session[ready.session.length - 1] * 100 : session?.returnAllPct ?? null;
  const backtestPct = ready ? ready.backtest[ready.backtest.length - 1] * 100 : null;
  const curveStart = ready ? ready.dates[0] : points[0]?.at ?? 0;
  const curveEnd = ready ? ready.dates[ready.dates.length - 1] : points[points.length - 1]?.at ?? 0;
  const fills = session ? fillsOf(orders.filter((o) => o.sessionId === session.id)) : [];
  const marks = curveEnd > curveStart ? rebalanceDays(fills).map((d) => (d.at - curveStart) / (curveEnd - curveStart)).filter((x) => x >= 0 && x <= 1) : [];
  const held = session
    ? positions
        .filter((p) => p.sessionId === session.id)
        .map((p) => ({ symbol: p.symbol, value: num(p.marketValue) }))
        .filter((p) => p.value > 0)
    : [];
  const heldTotal = held.reduce((t, p) => t + p.value, 0);

  const run = runs[id];
  const btPoints = pointsOf(run?.results?.equityCurve);
  const btBench = pointsOf(run?.results?.benchmarkEquityCurve);
  const btRet = run?.results?.metrics ? num(run.results.metrics.totalReturn) * 100 : backtestReturns[id];
  const benchSym = run?.results?.benchmarkSymbol || 'SPY';
  const benchRet = run?.results?.metrics?.benchmarkReturn?.value ? num(run.results.metrics.benchmarkReturn) * 100 : null;

  return (
    <Screen title={strategy.name} back={back} art="bold" artSeed={`strategy-${id}`}>
      <View style={s.status}>
        <StatusMark state={runState} label={statusLabel} />
        {session ? <ModeTag mode={session.mode} /> : null}
      </View>

      {session ? (
        <>
          <View style={s.money}>
            <Text variant="label" tone="fg3" style={s.caps}>{session.mode === 'live' ? 'LIVE SLEEVE' : 'PAPER SLEEVE'}</Text>
            <Text variant="hero">{session.value === null ? '–' : money(session.value, 2)}</Text>
            <Text variant="numSmall" tone="fg3">
              {session.today !== null ? <Text variant="numSmall" tone={pnlTone(session.today)}>{signedMoney(session.today, 2)} today  </Text> : null}
              {sessionPct !== null ? <Text variant="numSmall" tone={pnlTone(sessionPct)}>{pct(sessionPct, 1)}</Text> : null}
              {session.startedAt ? ` since ${shortDate(session.startedAt, thisYear)}` : ''}
            </Text>
          </View>
          {points.length > 1 ? (
            <Card style={s.bt}>
              <Curve values={ready ? ready.sessionValues : points.map((p) => p.value)} benchmark={ready?.backtestScaled} height={150} dot />
              {marks.length ? <MarkLane label="Rebalances" marks={marks} /> : null}
            </Card>
          ) : (
            <Text variant="small" tone="fg3">The curve appears after the session's first close.</Text>
          )}
          <LineKey
            main={session.mode === 'live' ? 'Live' : 'Paper'}
            dashed={backtestPct !== null && sessionPct !== null ? `Backtest, same dates ${pct(backtestPct, 1)} (${gapLabel(sessionPct, backtestPct)})` : undefined}
          />
          {same.status === 'none' ? <Text variant="caption" tone="fg3">No completed backtest covers these dates yet, so there's no dashed line.</Text> : null}

          <Card style={s.group}>
            <ListRow label="Rebalance" value={cadence(strategy.rebalance) || '–'} />
            <ListRow
              label="Holds"
              sub={held.length ? 'Positions now, %' : 'No positions yet'}
              right={
                <Text variant="numSmall" style={s.holds} numberOfLines={2}>
                  {held.map((p) => `${p.symbol} ${((p.value / heldTotal) * 100).toFixed(1)}`).join(' · ')}
                </Text>
              }
            />
            <ListRow
              label={`Version ${session.version ?? strategy.version}`}
              sub={session.version !== null && session.version !== strategy.version ? `Version ${strategy.version} is saved but not running` : 'The version this session runs'}
              onPress={() => router.push(`/builder/${id}`)}
              last
            />
          </Card>
        </>
      ) : (
        <>
          {btPoints.length > 1 ? (
            <Card style={s.bt}>
              <View style={s.line}>
                <Text variant="small" tone="fg3">Latest backtest</Text>
                {btRet !== undefined ? <Text variant="numStrong" tone={pnlTone(btRet)}>{pct(btRet, 1)}</Text> : null}
              </View>
              <Curve values={btPoints.map((p) => p.value)} benchmark={btBench.length > 1 ? btBench.map((p) => p.value) : undefined} height={120} />
              <AxisLabels labels={[shortDate(btPoints[0].at, 0), shortDate(btPoints[btPoints.length - 1].at, 0)]} />
              <LineKey main={`Backtest v${run?.strategyVersion ?? strategy.version}`} dashed={benchRet !== null ? `${benchSym} ${pct(benchRet, 1)}` : benchSym} />
              {stage.kind === 'neverRun' ? <Text variant="caption" tone="fg3">Backtested, never run on paper or live.</Text> : null}
            </Card>
          ) : runLoading[id] ? (
            <Loading label="Loading the latest backtest" />
          ) : (
            <Text variant="small" tone="fg3">No completed backtest yet.</Text>
          )}
          <Button label="Start on paper" onPress={() => router.push(`/sessions/start?strategy=${id}`)} />
        </>
      )}

      {read ? (
        <View style={s.rules}>
          <View style={s.line}>
            <Text variant="subhead">Rules</Text>
            <Text variant="small" tone="accent" onPress={() => router.push(`/builder/${id}`)}>Edit</Text>
          </View>
          <Card>
            <SentenceView sentences={read.sentences} onPick={() => router.push(`/builder/${id}`)} />
          </Card>
        </View>
      ) : null}

      <Card style={s.group}>
        <ListRow label="Backtest this strategy" onPress={() => router.push(`/backtests/new?strategy=${id}`)} />
        <ListRow label="All backtests" onPress={() => router.push('/backtests')} last />
      </Card>
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  status: { flexDirection: 'row', alignItems: 'center', gap: 10, marginTop: -6 },
  money: { gap: 2 },
  caps: { letterSpacing: 0.6, fontSize: 11 },
  group: { paddingVertical: 2 },
  holds: { flexShrink: 1, textAlign: 'right', maxWidth: '55%' },
  bt: { gap: 8 },
  line: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  rules: { gap: 8 },
}));
