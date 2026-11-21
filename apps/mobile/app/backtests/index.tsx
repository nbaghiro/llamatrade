import { num, pct } from '@llamatrade/core/format';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { router } from 'expo-router';
import { Plus } from 'lucide-react-native';
import { useEffect, useMemo } from 'react';
import { Pressable, View } from 'react-native';

import { Curve } from '../../src/backtests/charts';
import { listItem, loadRun, pointsOf, useLoad } from '../../src/backtests/data';
import { progressFraction, runTitle, splitRuns, type RunListItem } from '../../src/backtests/model';
import { shortDate } from '../../src/strategies/model';
import { makeStyles, useTheme } from '../../src/theme';
import { Card, EmptyState, ListRow, Loading, Meter, Notice, Screen, Text, pnlTone } from '../../src/ui';

const thisYear = new Date().getUTCFullYear();

function LatestCard({ item }: { item: RunListItem }) {
  const s = useStyles();
  const run = useLoad(item.id, () => loadRun(item.id));
  const full = run.status === 'ready' ? run.value : null;
  const m = full?.results?.metrics;
  const equity = pointsOf(full?.results?.equityCurve).map((p) => p.value);
  const bench = pointsOf(full?.results?.benchmarkEquityCurve).map((p) => p.value);
  const benchSym = full?.results?.benchmarkSymbol || 'SPY';
  const ret = m ? num(m.totalReturn) * 100 : item.ret !== null ? item.ret * 100 : null;
  const benchRet = m?.benchmarkReturn?.value ? num(m.benchmarkReturn) * 100 : null;
  return (
    <Card onPress={() => router.push(`/backtests/${item.id}`)} style={s.latest}>
      <View style={s.line}>
        <Text variant="small" tone="fg3" numberOfLines={1} style={s.flex}>{runTitle(item.name, item.version)} · {shortDate(item.at, thisYear)}</Text>
        <Text variant="small" tone="fg3">Backtest</Text>
      </View>
      <View style={s.figure}>
        <Text variant="hero" tone={ret === null ? 'fg3' : pnlTone(ret)}>{ret === null ? '–' : pct(ret, 1)}</Text>
        {benchRet !== null ? <Text variant="numSmall" tone="fg3">{benchSym} {pct(benchRet, 1)}</Text> : null}
      </View>
      {equity.length > 1 ? <Curve values={equity} benchmark={bench.length > 1 ? bench : undefined} height={130} /> : run.status === 'loading' ? <Loading label="Loading the curve" /> : null}
      {m ? (
        <View style={s.stats}>
          <Text variant="small" tone="fg3">Sharpe <Text variant="numStrong">{num(m.sharpeRatio).toFixed(2)}</Text></Text>
          <Text variant="small" tone="fg3">Worst <Text variant="numStrong" tone="loss">{pct(-Math.abs(num(m.maxDrawdown)) * 100, 1)}</Text></Text>
        </View>
      ) : null}
    </Card>
  );
}

export default function BacktestsScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { history, loadHistory, currentBacktest, streaming, progress } = useBacktestStore();
  const { strategies, fetchStrategies } = useStrategiesStore();

  useEffect(() => {
    loadHistory();
    if (!useStrategiesStore.getState().strategies.length) fetchStrategies();
  }, [loadHistory, fetchStrategies]);

  const nameOf = (id: string) => strategies.find((st) => st.id === id)?.name ?? 'Strategy';
  const items = useMemo(
    () => history.runs.map((r) => listItem(r, strategies.find((st) => st.id === r.strategyId)?.name ?? 'Strategy', history.metrics[r.id])),
    [history.runs, history.metrics, strategies],
  );
  const { running, latest, earlier } = splitRuns(items);
  const watching = streaming && currentBacktest ? currentBacktest : null;
  const back = { label: 'Strategies', onPress: () => (router.canGoBack() ? router.back() : router.replace('/strategies')) };

  return (
    <Screen
      title="Backtests"
      back={back}
      art="bold"
      artSeed="backtests-index"
      refreshing={history.loading && history.loaded}
      onRefresh={() => loadHistory()}
      right={
        <Pressable accessibilityRole="button" accessibilityLabel="New backtest" hitSlop={8} onPress={() => router.push('/backtests/new')}>
          <Plus color={c.fg} size={24} strokeWidth={1.6} />
        </Pressable>
      }
    >
      {watching ? (
        <Card onPress={() => router.push(`/backtests/${watching.id}`)} style={s.running}>
          <View style={s.dot} />
          <Text variant="small" numberOfLines={1} style={s.runName}>{runTitle(nameOf(watching.strategyId), watching.strategyVersion)}</Text>
          <View style={s.flex}><Meter value={progressFraction(progress)} /></View>
          <Text variant="numSmall" tone="fg2">{Math.round(progress)}%</Text>
        </Card>
      ) : null}
      {!watching && running.length ? (
        <Card style={s.group}>
          {running.map((r, i) => (
            <ListRow key={r.id} label={runTitle(r.name, r.version)} sub="Running" onPress={() => router.push(`/backtests/${r.id}`)} last={i === running.length - 1} />
          ))}
        </Card>
      ) : null}

      {history.error ? <Notice title="Backtests could not be loaded." detail={history.error} onPress={() => loadHistory()} /> : null}

      {!history.loaded ? (
        <Loading label="Loading backtests" />
      ) : !items.length && !history.error ? (
        <EmptyState title="No backtests yet" detail="Run one from a strategy to see how its rules would have done." />
      ) : (
        <>
          {latest ? <LatestCard item={latest} /> : null}
          {earlier.length ? (
            <View style={s.section}>
              <View style={s.line}>
                <Text variant="subhead">Earlier</Text>
                <Text variant="small" tone="fg3">{history.total} in all</Text>
              </View>
              <Card style={s.group}>
                {earlier.slice(0, 20).map((r, i, arr) => (
                  <ListRow
                    key={r.id}
                    label={runTitle(r.name, r.version)}
                    sub={`${shortDate(r.at, thisYear)}${r.sharpe !== null ? ` · Sharpe ${r.sharpe.toFixed(2)}` : r.state === 'failed' ? ' · Couldn’t finish' : r.state === 'cancelled' ? ' · Cancelled' : ''}`}
                    right={r.ret !== null ? <Text variant="numSmall" tone={pnlTone(r.ret)}>{pct(r.ret * 100, 1)}</Text> : <Text variant="numSmall" tone="fg3">–</Text>}
                    onPress={() => router.push(`/backtests/${r.id}`)}
                    last={i === arr.length - 1}
                  />
                ))}
              </Card>
            </View>
          ) : null}
        </>
      )}
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  running: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, backgroundColor: t.c.accentSoft, borderColor: t.c.accentSoft },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: t.c.accent },
  runName: { maxWidth: 140 },
  latest: { gap: 8 },
  line: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  figure: { flexDirection: 'row', alignItems: 'baseline', gap: 10 },
  stats: { flexDirection: 'row', gap: 18 },
  flex: { flex: 1 },
  section: { gap: 8, marginTop: 6 },
  group: { paddingVertical: 2 },
}));
