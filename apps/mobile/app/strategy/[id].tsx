import { num, pct } from '@llamatrade/core/format';
import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { StrategyStatus } from '@llamatrade/core/proto/strategy_pb';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect } from 'react';
import { View } from 'react-native';

import { LineChart } from '../../src/charts/LineChart';
import { timeLabels } from '../../src/charts/paths';
import { DslBlock } from '../../src/copilot/DslBlock';
import { makeStyles, useTheme } from '../../src/theme';
import { Button, Card, ListRow, Loading, PanelError, Screen, StatusMark, Text, WeightStrip, pnlTone } from '../../src/ui';
import { cadence, runStateOfStrategy } from '../../src/ui/status';

/** Per-asset weights (%) from a backtest's final holdings, largest first. */
function positionAllocations(run: BacktestRun | null | undefined): { symbol: string; weight: number }[] {
  const positions = run?.results?.finalPositions ?? [];
  const valued = positions
    .map((p) => ({ symbol: p.symbol, value: num(p.marketValue) || num(p.quantity) * num(p.currentPrice) }))
    .filter((p) => p.value > 0);
  const total = valued.reduce((s, p) => s + p.value, 0);
  if (total <= 0) return [];
  return valued.map((p) => ({ symbol: p.symbol, weight: (p.value / total) * 100 })).sort((a, b) => b.weight - a.weight);
}

function Metric({ label, value, tone }: { label: string; value: string; tone?: 'gain' | 'loss' | 'fg' | 'fg3' }) {
  const s = useStyles();
  return (
    <View style={s.metric}>
      <Text variant="label" tone="fg3">{label}</Text>
      <Text variant="numLarge" tone={tone ?? 'fg'}>{value}</Text>
    </View>
  );
}

const back = { label: 'Strategies', onPress: () => (router.canGoBack() ? router.back() : router.replace('/strategies')) };

export default function StrategyDetailScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const {
    strategies,
    details,
    detailLoading,
    deployments,
    backtestReturns,
    runs,
    runLoading,
    fetchStrategyDetail,
    fetchStrategyRun,
    activateStrategy,
    pauseStrategy,
  } = useStrategiesStore();

  useEffect(() => {
    if (!id) return;
    fetchStrategyDetail(id);
    fetchStrategyRun(id);
    // Opened from Portfolio or Home: the list and deployment figures may not be loaded yet.
    const store = useStrategiesStore.getState();
    if (store.strategies.length === 0) store.fetchStrategies();
    if (Object.keys(store.deployments).length === 0) store.fetchDeployments();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const summary = strategies.find((x) => x.id === id);
  const strategy = (id ? details[id] : undefined) ?? summary;

  if (!strategy) {
    return (
      <Screen title="Strategy" back={back}>
        {id && detailLoading[id] ? (
          <Loading label="Loading strategy" />
        ) : (
          <PanelError title="Couldn't find this strategy" detail="It may have been archived or removed." onRetry={id ? () => fetchStrategyDetail(id) : undefined} />
        )}
      </Screen>
    );
  }

  const dep = deployments[strategy.id];
  const deployed = dep !== undefined;
  const run = id ? runs[id] : undefined;
  const loadingRun = id ? runLoading[id] : false;
  const loadingDsl = id ? detailLoading[id] : false;
  const metrics = run?.results?.metrics;

  const btReturn = metrics ? num(metrics.totalReturn) * 100 : id ? backtestReturns[id] : undefined;
  const returnPct = deployed ? dep.returnAll : (btReturn ?? null);
  const sharpe = metrics ? num(metrics.sharpeRatio) : null;
  const maxDD = metrics ? num(metrics.maxDrawdown) * 100 : null;
  const benchReturn = metrics ? num(metrics.benchmarkReturn) * 100 : null;

  const equity = (run?.results?.equityCurve ?? []).map((p) => num(p.equity));
  const equityTimes = (run?.results?.equityCurve ?? []).map((p) => Number(p.timestamp?.seconds ?? 0));
  const bench = (run?.results?.benchmarkEquityCurve ?? []).map((p) => num(p.equity));
  const benchSym = (run?.results?.benchmarkSymbol || strategy.dslCode.match(/:benchmark\s+([A-Za-z]+)/)?.[1] || 'SPY').toUpperCase();
  const positions = positionAllocations(run);
  const live = dep?.mode === ExecutionMode.LIVE;

  return (
    <Screen title={strategy.name} back={back} eyebrow={`Strategy · ${live ? 'Live' : 'Paper'}`}>
      <View style={s.statusLine}>
        <StatusMark state={runStateOfStrategy(strategy.status, dep?.status)} />
        {strategy.templateId ? <Text variant="small" tone="fg3">From a template</Text> : null}
      </View>

      {strategy.description ? <Text variant="small" tone="fg2">{strategy.description}</Text> : null}

      <Card style={s.metrics}>
        <Metric
          label={deployed || returnPct === null ? 'Return' : 'Backtest'}
          value={returnPct === null ? '–' : pct(returnPct, 1)}
          tone={returnPct === null ? 'fg3' : pnlTone(returnPct) === 'loss' ? 'loss' : 'gain'}
        />
        <Metric label="Sharpe" value={sharpe === null ? '–' : sharpe.toFixed(2)} tone={sharpe === null ? 'fg3' : 'fg'} />
        <Metric
          label="Max DD"
          value={maxDD === null ? '–' : `−${Math.abs(maxDD).toFixed(1)}%`}
          tone={maxDD === null ? 'fg3' : 'loss'}
        />
      </Card>

      {equity.length > 1 ? (
        <Card style={s.chartCard}>
          <LineChart values={equity} benchmark={bench.length > 1 ? bench : undefined} height={140} axis xLabels={timeLabels(equityTimes)} />
          <View style={s.legend}>
            <View style={s.legendItem}>
              <View style={[s.swatch, { backgroundColor: c.accent }]} />
              <Text variant="numSmall" tone="fg2">Strategy {returnPct === null ? '' : pct(returnPct, 1)}</Text>
            </View>
            {bench.length > 1 ? (
              <View style={s.legendItem}>
                <View style={[s.swatch, { backgroundColor: c.fg3 }]} />
                <Text variant="numSmall" tone="fg2">{benchSym} {benchReturn === null ? '' : pct(benchReturn, 1)}</Text>
              </View>
            ) : null}
          </View>
        </Card>
      ) : loadingRun ? (
        <Card><Loading label="Loading the latest backtest" /></Card>
      ) : null}

      <Card style={s.holdings}>
        <Text variant="label" tone="fg3">Holdings</Text>
        {positions.length ? (
          <>
            <WeightStrip weights={positions.map((p) => p.weight)} />
            <View style={s.holdingLabels}>
              {positions.map((p) => (
                <Text key={p.symbol} variant="numSmall" tone="fg2">
                  <Text variant="numSmall" tone="fg">{p.symbol}</Text> {p.weight.toFixed(1)}%
                </Text>
              ))}
            </View>
          </>
        ) : (
          <Text variant="small" tone="fg3">No holdings yet. Run a backtest on the web to see what it would hold.</Text>
        )}
      </Card>

      <Card style={s.rows}>
        <ListRow
          label="Universe"
          right={
            <Text variant="numSmall" style={s.universe} numberOfLines={2}>
              {strategy.symbols.length ? strategy.symbols.join(' ') : '–'}
            </Text>
          }
        />
        <ListRow label="Rebalance" value={cadence(strategy.rebalance) || '–'} />
        <ListRow label="Benchmark" right={<Text variant="numSmall">{benchSym}</Text>} />
        <ListRow label="Version" right={<Text variant="numSmall">{String(strategy.version)}</Text>} last />
      </Card>

      <View style={s.definition}>
        <Text variant="label" tone="fg3">Definition</Text>
        {strategy.dslCode ? (
          <DslBlock code={strategy.dslCode} />
        ) : loadingDsl ? (
          <Card><Loading label="Loading the definition" /></Card>
        ) : (
          <PanelError
            title="Couldn't load the definition"
            detail="The strategy service didn't respond."
            onRetry={id ? () => fetchStrategyDetail(id) : undefined}
          />
        )}
      </View>

      {strategy.status === StrategyStatus.ACTIVE ? (
        <Button label="Pause strategy" variant="secondary" onPress={() => pauseStrategy(strategy.id)} />
      ) : strategy.status === StrategyStatus.PAUSED ? (
        <Button label="Resume strategy" onPress={() => activateStrategy(strategy.id)} />
      ) : null}

      <Text variant="caption" tone="fg3" style={s.footnote}>
        Edit the strategy and run backtests in the web builder.
      </Text>
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  statusLine: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: -6 },
  metrics: { flexDirection: 'row', gap: 8 },
  metric: { flex: 1, gap: 4 },
  chartCard: { paddingHorizontal: 12, gap: 10 },
  legend: { flexDirection: 'row', gap: 16 },
  legendItem: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  swatch: { width: 12, height: 2, borderRadius: 1 },
  holdings: { gap: 10 },
  holdingLabels: { flexDirection: 'row', flexWrap: 'wrap', columnGap: 14, rowGap: 4 },
  rows: { paddingVertical: 2 },
  universe: { flexShrink: 1, textAlign: 'right', maxWidth: '65%' },
  definition: { gap: 8 },
  footnote: { textAlign: 'center' },
}));
