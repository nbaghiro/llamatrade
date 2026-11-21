import { money } from '@llamatrade/core/format';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { DEFAULT_BACKTEST_COSTS, useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { TextInput, View } from 'react-native';

import { loadDailyCloses } from '../../src/backtests/bars';
import { AxisLabels, Curve, Lanes } from '../../src/backtests/charts';
import { isoDay, presetRange, rebalanceCount, RANGE_PRESETS, type Point, type RangePreset } from '../../src/backtests/model';
import { Sheet } from '../../src/builder/Sheet';
import { shortDate } from '../../src/strategies/model';
import { fonts, makeStyles, useTheme } from '../../src/theme';
import { Button, Card, ListRow, Loading, Notice, Screen, Segmented, Text } from '../../src/ui';
import { cadence } from '../../src/ui/status';

const DAY = 86_400_000;
const LOOKBACK_YEARS = 10;
const MAX_LANES = 6;

type Coverage = { status: 'loading' } | { status: 'ready'; spy: Point[]; first: Record<string, number | null> } | { status: 'error' };

/** SPY over ten years for the range chart, and the first daily bar each symbol has in that window. */
function useCoverage(symbols: readonly string[], today: number): Coverage {
  const [state, setState] = useState<Coverage>({ status: 'loading' });
  const key = symbols.join(',');
  useEffect(() => {
    let live = true;
    const from = today - LOOKBACK_YEARS * 365.25 * DAY;
    setState({ status: 'loading' });
    const shown = symbols.slice(0, MAX_LANES);
    Promise.all([loadDailyCloses('SPY', from, today), ...shown.map((sym) => loadDailyCloses(sym, from, today).catch(() => null))])
      .then(([spy, ...rest]) => {
        if (!live) return;
        const first: Record<string, number | null> = {};
        shown.forEach((sym, i) => {
          const bars = rest[i];
          first[sym] = bars && bars.length ? bars[0].at : null;
        });
        setState({ status: 'ready', spy, first });
      })
      .catch(() => live && setState({ status: 'error' }));
    return () => {
      live = false;
    };
    // `symbols` is identified by `key`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key, today]);
  return state;
}

function fmtDay(t: number): string {
  return shortDate(t, 0);
}

export default function NewBacktestScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const params = useLocalSearchParams<{ strategy?: string; version?: string }>();
  const { strategies, fetchStrategies } = useStrategiesStore();
  const { setConfig, runBacktest, loading, error, clearError } = useBacktestStore();
  const [strategyId, setStrategyId] = useState<string | undefined>(params.strategy);
  const [preset, setPreset] = useState<RangePreset>('5Y');
  const [capital, setCapital] = useState('25000');
  const [picking, setPicking] = useState(false);
  const today = useMemo(() => Math.floor(Date.now() / DAY) * DAY, []);

  useEffect(() => {
    if (!useStrategiesStore.getState().strategies.length) fetchStrategies();
    clearError();
  }, [fetchStrategies, clearError]);

  const strategy: Strategy | undefined = strategies.find((x) => x.id === strategyId) ?? (strategyId ? undefined : strategies[0]);
  const version = params.version && strategy?.id === params.strategy ? Number(params.version) : strategy?.version ?? 0;
  const symbols = useMemo(() => [...new Set((strategy?.symbols ?? []).map((x) => x.toUpperCase()))].filter((x) => x !== 'SPY'), [strategy]);
  const coverage = useCoverage(symbols, today);

  const latestFirst =
    coverage.status === 'ready'
      ? Object.values(coverage.first).reduce<number | null>((m, t) => (t === null ? m : m === null ? t : Math.max(m, t)), null)
      : null;
  const range = presetRange(preset, today, preset === 'Max' ? latestFirst : null);
  const spyFirst = coverage.status === 'ready' && coverage.spy.length ? coverage.spy[0].at : null;
  const missing =
    coverage.status === 'ready' && spyFirst !== null
      ? Object.entries(coverage.first).filter(([, t]) => t === null || (t > spyFirst + 7 * DAY && t > range.start + 7 * DAY))
      : [];
  const historyShort = spyFirst !== null && spyFirst > range.start + 7 * DAY;
  const count = strategy ? rebalanceCount(strategy.rebalance, range.start, range.end) : null;

  const spy = coverage.status === 'ready' ? coverage.spy : [];
  const chartStart = spy[0]?.at ?? today - LOOKBACK_YEARS * 365.25 * DAY;
  const span = today - chartStart;
  const selectFrom = span > 0 ? Math.max(0, (range.start - chartStart) / span) : 0;
  const lanes =
    coverage.status === 'ready'
      ? Object.entries(coverage.first).map(([symbol, first]) => ({
          symbol,
          spans: first === null ? [] : [{ from: Math.max(0, (first - chartStart) / span), to: 1 }],
        }))
      : [];
  const capitalN = Number(capital.replace(/[^0-9.]/g, ''));

  const run = async () => {
    if (!strategy) return;
    setConfig({
      strategyId: strategy.id,
      strategyVersion: version || undefined,
      startDate: isoDay(range.start),
      endDate: isoDay(range.end),
      initialCapital: capitalN > 0 ? capitalN : 25000,
      symbols: [],
      commission: DEFAULT_BACKTEST_COSTS.commission,
      slippage: DEFAULT_BACKTEST_COSTS.slippage,
      timeframe: '1D',
      benchmarkSymbol: 'SPY',
    });
    const id = await runBacktest();
    if (id) router.replace(`/backtests/${id}`);
  };

  const back = { label: 'Backtests', onPress: () => (router.canGoBack() ? router.back() : router.replace('/backtests')) };

  return (
    <Screen title="New backtest" back={back} art="bold" artSeed="backtest-new">
      <Card style={s.group}>
        <ListRow
          label={strategy?.name ?? 'Choose a strategy'}
          sub={strategy ? `Version ${version}${cadence(strategy.rebalance) ? ` · rebalances ${strategy.rebalance.toLowerCase()}` : ''}` : undefined}
          onPress={() => setPicking(true)}
          last
        />
      </Card>

      <View style={s.rangeHead}>
        <Text variant="label" tone="fg3" style={s.caps}>DATE RANGE</Text>
        <Text variant="numLarge">{fmtDay(range.start)} → {fmtDay(range.end)}</Text>
        {count !== null && strategy ? <Text variant="small" tone="fg3">About {count} {strategy.rebalance.toLowerCase()} rebalances</Text> : null}
      </View>

      {coverage.status === 'loading' ? (
        <Loading label="Loading price history" />
      ) : coverage.status === 'error' ? (
        <Notice tone="neutral" title="Price history could not be loaded." detail="You can still run the backtest; the service checks the data when it starts." />
      ) : (
        <View>
          <Curve values={spy.map((p) => p.value)} height={110} selectFrom={selectFrom} />
          <Lanes lanes={[{ symbol: 'SPY', spans: [{ from: 0, to: 1 }] }, ...lanes].slice(0, MAX_LANES)} marker={{ at: selectFrom, tone: 'fg' }} />
          <AxisLabels labels={spy.length ? [String(new Date(chartStart).getUTCFullYear()), String(new Date(today).getUTCFullYear())] : []} />
        </View>
      )}

      <Segmented options={RANGE_PRESETS.map((p) => ({ key: p, label: p }))} value={preset} onChange={setPreset} fill />

      {missing.length ? (
        <Notice
          title={`${missing.map(([sym]) => sym).join(', ')} ${missing.length === 1 ? 'starts' : 'start'} later than SPY.`}
          detail={missing
            .map(([sym, t]) => (t === null ? `${sym}: no daily bars in the last ten years.` : `${sym}: first bar ${fmtDay(t)}.`))
            .join(' ') + ' Choose a shorter range, or the run may stop when it needs them.'}
        />
      ) : null}

      {historyShort && spyFirst !== null ? (
        <Text variant="caption" tone="fg3">Prices on this server start {fmtDay(spyFirst)}, so the chart shows less than the range.</Text>
      ) : null}

      <Card style={s.group}>
        <ListRow
          label="Starting capital"
          right={
            <TextInput
              value={capital}
              onChangeText={setCapital}
              keyboardType="number-pad"
              style={[s.input, { color: c.fg }]}
              accessibilityLabel="Starting capital in dollars"
            />
          }
        />
        <ListRow label="Benchmark" right={<Text variant="numSmall">SPY</Text>} />
        <ListRow
          label="Costs"
          right={<Text variant="numSmall" tone="fg3">{money(DEFAULT_BACKTEST_COSTS.commission, 3)} a fill + {(DEFAULT_BACKTEST_COSTS.slippage * 100).toFixed(1)}%</Text>}
          last
        />
      </Card>

      {error ? <Notice title="The backtest didn't start." detail={error} /> : null}

      <Text variant="caption" tone="fg3" style={s.center}>
        {coverage.status === 'ready' && !missing.length && symbols.length
          ? 'Every symbol has prices from the same day as SPY.'
          : `${money(capitalN > 0 ? capitalN : 25000)} on paper, simulated on daily bars.`}
      </Text>
      <Button label="Run backtest" onPress={run} loading={loading} disabled={!strategy} />

      <Sheet visible={picking} onClose={() => setPicking(false)}>
        <Text variant="subhead">Strategy</Text>
        <View>
          {strategies.map((st, i) => (
            <ListRow
              key={st.id}
              label={st.name}
              sub={`Version ${st.version}`}
              onPress={() => {
                setStrategyId(st.id);
                setPicking(false);
              }}
              last={i === strategies.length - 1}
            />
          ))}
        </View>
      </Sheet>
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  group: { paddingVertical: 2 },
  rangeHead: { gap: 4 },
  caps: { letterSpacing: 0.6, fontSize: 11 },
  input: { fontFamily: fonts.mono, fontSize: 14, minWidth: 90, textAlign: 'right', padding: 0 },
  center: { textAlign: 'center' },
}));
