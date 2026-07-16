import { isUp, num, pct } from '@llamatrade/core/format';
import type { BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { StrategyStatus } from '@llamatrade/core/proto/strategy_pb';
import { useStrategiesStore, type StrategyDeployment } from '@llamatrade/core/stores/strategies';
import { router, useLocalSearchParams } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import { X } from 'lucide-react-native';
import { useEffect } from 'react';
import { ActivityIndicator, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { LineChart } from '../../src/charts/LineChart';
import { DslBlock } from '../../src/copilot/DslBlock';
import { fonts, palette, strategyColors } from '../../src/theme';
import { Body, Display, Label, Mono } from '../../src/ui';

type PillVariant = 'gray' | 'orange' | 'ink' | 'green';
function statusPill(status: StrategyStatus, dep: StrategyDeployment | undefined): { label: string; variant: PillVariant } {
  switch (status) {
    case StrategyStatus.PAUSED:
      return { label: 'PAUSED', variant: 'ink' };
    case StrategyStatus.ARCHIVED:
      return { label: 'ARCHIVED', variant: 'gray' };
    case StrategyStatus.ACTIVE:
      return dep?.mode === ExecutionMode.LIVE ? { label: 'LIVE', variant: 'green' } : { label: 'PAPER', variant: 'orange' };
    default:
      return { label: 'DRAFT', variant: 'gray' };
  }
}

const PILL_BG: Record<PillVariant, { bg: string; fg: string }> = {
  gray: { bg: palette.bone, fg: palette.ink },
  orange: { bg: palette.orange[500], fg: palette.ink },
  ink: { bg: palette.paper, fg: palette.ink },
  green: { bg: palette.green[500], fg: palette.bone },
};

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

function Chip({ label, bg, fg }: { label: string; bg?: string; fg?: string }) {
  return (
    <View
      style={{
        borderWidth: 1.5,
        borderColor: bg ? palette.ink : 'rgba(251,248,241,0.3)',
        backgroundColor: bg ?? 'transparent',
        paddingHorizontal: 7,
        paddingVertical: 3,
      }}
    >
      <Mono size={9} color={fg ?? palette.bone} style={{ fontWeight: '700', letterSpacing: 0.5 }}>
        {label}
      </Mono>
    </View>
  );
}

function Metric({ label, value, color, note }: { label: string; value: string; color?: string; note?: string }) {
  return (
    <View style={{ flex: 1, padding: 11 }}>
      <Mono size={9} color={palette.gray[500]} style={{ fontWeight: '700', letterSpacing: 0.6 }}>
        {label}
      </Mono>
      <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 3, marginTop: 4 }}>
        <Display size={20} color={color ?? palette.ink}>{value}</Display>
        {note ? <Mono size={8} color={palette.gray[400]}>{note}</Mono> : null}
      </View>
    </View>
  );
}

export default function StrategyDetailScreen() {
  const insets = useSafeAreaInsets();
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
    if (id) {
      void fetchStrategyDetail(id);
      void fetchStrategyRun(id);
    }
  }, [id, fetchStrategyDetail, fetchStrategyRun]);

  const summary = strategies.find((s) => s.id === id);
  const strategy = (id ? details[id] : undefined) ?? summary;

  if (!strategy) {
    return (
      <View style={{ flex: 1, backgroundColor: palette.ink, paddingTop: insets.top }}>
        <StatusBar style="light" />
        <View style={{ padding: 14, flexDirection: 'row', justifyContent: 'space-between' }}>
          <Mono size={9} color={palette.orange[500]} style={{ fontWeight: '700' }}>STRATEGY DETAIL</Mono>
          <Pressable onPress={() => router.back()} hitSlop={10}><X color={palette.bone} size={20} strokeWidth={2.5} /></Pressable>
        </View>
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', backgroundColor: palette.bone }}>
          {id && detailLoading[id] ? <ActivityIndicator color={palette.ink} /> : <Label>Strategy not found</Label>}
        </View>
      </View>
    );
  }

  const dep = deployments[strategy.id];
  const deployed = dep !== undefined;
  const run = id ? runs[id] : undefined;
  const loadingRun = id ? runLoading[id] : false;
  const loadingDsl = id ? detailLoading[id] : false;
  const metrics = run?.results?.metrics;

  const btReturn = metrics ? num(metrics.totalReturn) * 100 : id ? backtestReturns[id] : undefined;
  const returnPct = deployed ? dep.returnAll : btReturn ?? null;
  const returnIsBacktest = !deployed && btReturn !== undefined;
  const up = returnPct !== null && isUp(returnPct);
  const sharpe = metrics ? num(metrics.sharpeRatio) : null;
  const maxDD = metrics ? num(metrics.maxDrawdown) * 100 : null;
  const benchReturn = metrics ? num(metrics.benchmarkReturn) * 100 : null;

  const equity = (run?.results?.equityCurve ?? []).map((p) => num(p.equity));
  const bench = (run?.results?.benchmarkEquityCurve ?? []).map((p) => num(p.equity));
  const benchSym = run?.results?.benchmarkSymbol || strategy.dslCode.match(/:benchmark\s+([A-Za-z]+)/)?.[1] || 'SPY';
  const dsl = strategy.dslCode || strategy.compiledJson;
  const positions = positionAllocations(run);
  const pill = statusPill(strategy.status, dep);
  const pc = PILL_BG[pill.variant];
  const impl = strategy.templateId ? 'TEMPLATE' : 'DSL';
  const idx = strategies.findIndex((s) => s.id === strategy.id);
  const accent = dep?.color || strategyColors[(idx < 0 ? 0 : idx) % strategyColors.length];

  return (
    <View style={{ flex: 1, backgroundColor: palette.bone }}>
      <StatusBar style="light" />
      {/* Ink header */}
      <View style={{ backgroundColor: palette.ink, paddingTop: insets.top + 10, paddingHorizontal: 14, paddingBottom: 14 }}>
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
          <Mono size={9} color={palette.orange[500]} style={{ fontWeight: '700', letterSpacing: 1 }}>STRATEGY DETAIL</Mono>
          <Pressable onPress={() => router.back()} hitSlop={10}><X color={palette.bone} size={20} strokeWidth={2.5} /></Pressable>
        </View>
        <Body size={26} color={palette.bone} style={{ fontFamily: fonts.display, textTransform: 'uppercase', marginTop: 6 }} numberOfLines={2}>
          {strategy.name}
        </Body>
        <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginTop: 11 }}>
          <Chip label={pill.label} bg={pc.bg} fg={pc.fg} />
          <Chip label={impl} />
          <Chip label={(strategy.timeframe || '1D').toUpperCase()} />
          <Chip label={`${strategy.symbols.length} SYMBOLS`} />
          <Chip label={`V${strategy.version}`} />
          <Chip label={`BENCH · ${benchSym.toUpperCase()}`} />
        </View>
      </View>

      <ScrollView contentContainerStyle={{ padding: 12, gap: 12 }} showsVerticalScrollIndicator={false}>
        {strategy.description ? (
          <Body size={13} color={palette.gray[600]} style={{ lineHeight: 19 }}>{strategy.description}</Body>
        ) : null}

        {/* Metrics */}
        <View style={{ flexDirection: 'row', borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.paper }}>
          <Metric
            label="RETURN"
            value={returnPct === null ? '—' : `${returnPct >= 0 ? '+' : ''}${returnPct.toFixed(1)}%`}
            color={returnPct === null ? palette.gray[400] : up ? palette.green[500] : palette.red[500]}
            note={returnIsBacktest ? 'bt' : undefined}
          />
          <View style={{ width: 2, backgroundColor: palette.ink }} />
          <Metric label="SHARPE" value={sharpe === null ? '—' : sharpe.toFixed(2)} />
          <View style={{ width: 2, backgroundColor: palette.ink }} />
          <Metric label="MAX DD" value={maxDD === null ? '—' : `-${Math.abs(maxDD).toFixed(1)}%`} color={maxDD === null ? palette.gray[400] : palette.red[500]} />
        </View>

        {/* Equity curve */}
        {equity.length > 1 ? (
          <View style={{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.paper, padding: 12, gap: 8 }}>
            <LineChart values={equity} benchmark={bench.length > 1 ? bench : undefined} height={120} color={palette.green[500]} fill="rgba(15,122,52,0.10)" />
            <View style={{ flexDirection: 'row', gap: 16, marginTop: 2 }}>
              <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                <View style={{ width: 14, height: 3, backgroundColor: palette.green[500] }} />
                <Mono size={9} color={palette.gray[600]}>STRATEGY {returnPct === null ? '' : `${returnPct >= 0 ? '+' : ''}${returnPct.toFixed(1)}%`}</Mono>
              </View>
              {bench.length > 1 ? (
                <View style={{ flexDirection: 'row', alignItems: 'center', gap: 5 }}>
                  <View style={{ width: 14, height: 3, backgroundColor: palette.gray[400] }} />
                  <Mono size={9} color={palette.gray[600]}>{benchSym.toUpperCase()} {benchReturn === null ? '' : `${benchReturn >= 0 ? '+' : ''}${benchReturn.toFixed(1)}%`}</Mono>
                </View>
              ) : null}
            </View>
          </View>
        ) : loadingRun ? (
          <View style={{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.paper, padding: 30, alignItems: 'center' }}>
            <ActivityIndicator color={palette.ink} />
          </View>
        ) : null}

        {/* DSL */}
        <View style={{ gap: 6 }}>
          <Label style={{ marginLeft: 2 }}>Definition · DSL</Label>
          {dsl ? (
            <DslBlock code={dsl} />
          ) : loadingDsl ? (
            <View style={{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.ink, padding: 18, alignItems: 'center' }}>
              <ActivityIndicator color={palette.orange[500]} />
            </View>
          ) : (
            <Pressable
              onPress={() => id && void fetchStrategyDetail(id)}
              style={{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.bone2, padding: 14, alignItems: 'center', gap: 4 }}
            >
              <Mono size={10} color={palette.gray[600]}>Couldn’t load definition</Mono>
              <Mono size={9} color={palette.orange[500]} style={{ fontWeight: '700' }}>TAP TO RETRY</Mono>
            </Pressable>
          )}
        </View>

        {/* Allocation */}
        <View style={{ gap: 6 }}>
          <Label style={{ marginLeft: 2 }}>Allocation · {positions.length} {positions.length === 1 ? 'position' : 'positions'}</Label>
          {positions.length ? (
            <View style={{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.paper, padding: 12, gap: 8 }}>
              {positions.map((p) => (
                <View key={p.symbol}>
                  <View style={{ flexDirection: 'row', justifyContent: 'space-between' }}>
                    <Mono size={11} style={{ fontWeight: '700' }}>{p.symbol}</Mono>
                    <Mono size={11} color={palette.gray[600]}>{p.weight.toFixed(1)}%</Mono>
                  </View>
                  <View style={{ height: 6, borderWidth: 1.5, borderColor: palette.ink, backgroundColor: palette.bone, marginTop: 3 }}>
                    <View style={{ height: '100%', width: `${Math.min(100, p.weight)}%`, backgroundColor: accent }} />
                  </View>
                </View>
              ))}
            </View>
          ) : (
            <View style={{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.bone2, padding: 14 }}>
              <Mono size={10} color={palette.gray[500]}>No position data — run a backtest to populate holdings.</Mono>
            </View>
          )}
        </View>

        {/* Universe */}
        {strategy.symbols.length ? (
          <View style={{ gap: 6 }}>
            <Label style={{ marginLeft: 2 }}>Universe</Label>
            <View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 6 }}>
              {strategy.symbols.map((sym) => (
                <View key={sym} style={{ borderWidth: 1.5, borderColor: palette.ink, backgroundColor: palette.paper, paddingHorizontal: 8, paddingVertical: 4 }}>
                  <Mono size={10} style={{ fontWeight: '700' }}>{sym}</Mono>
                </View>
              ))}
            </View>
          </View>
        ) : null}

        {/* Actions */}
        {strategy.status === StrategyStatus.ACTIVE ? (
          <Pressable onPress={() => void pauseStrategy(strategy.id)} style={{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.paper, paddingVertical: 12, alignItems: 'center', marginTop: 2 }}>
            <Mono size={11} style={{ fontWeight: '700' }}>PAUSE STRATEGY</Mono>
          </Pressable>
        ) : strategy.status === StrategyStatus.PAUSED ? (
          <Pressable onPress={() => void activateStrategy(strategy.id)} style={{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.orange[500], paddingVertical: 12, alignItems: 'center', marginTop: 2 }}>
            <Mono size={11} style={{ fontWeight: '700' }}>ACTIVATE STRATEGY</Mono>
          </Pressable>
        ) : null}

        <Mono size={9} color={palette.gray[500]} style={{ textAlign: 'center', marginTop: 2, marginBottom: 8 }}>
          EDIT & RUN BACKTESTS IN THE DESKTOP BUILDER
        </Mono>
      </ScrollView>
    </View>
  );
}
