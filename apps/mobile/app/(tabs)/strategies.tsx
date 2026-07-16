import { useStrategiesStore, type StrategyDeployment } from '@llamatrade/core/stores/strategies';
import { isUp, moneyShort, num, pct } from '@llamatrade/core/format';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { StrategyStatus, type Strategy } from '@llamatrade/core/proto/strategy_pb';
import { router } from 'expo-router';
import { ChevronRight } from 'lucide-react-native';
import { useEffect } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { palette, strategyColors } from '../../src/theme';
import { Badge, Body, Card, Display, Label, Mono } from '../../src/ui';

type Pill = { label: string; variant: 'gray' | 'orange' | 'ink' | 'green' };

function pillFor(status: StrategyStatus, dep: StrategyDeployment | undefined): Pill {
  switch (status) {
    case StrategyStatus.PAUSED:
      return { label: 'Paused', variant: 'ink' };
    case StrategyStatus.ARCHIVED:
      return { label: 'Archived', variant: 'gray' };
    case StrategyStatus.ACTIVE:
      return dep?.mode === ExecutionMode.LIVE
        ? { label: 'Live', variant: 'green' }
        : { label: 'Paper', variant: 'orange' };
    default:
      return { label: 'Draft', variant: 'gray' };
  }
}

const FILTERS: { key: string; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'paused', label: 'Paused' },
  { key: 'draft', label: 'Draft' },
];

function StrategyCard({
  strategy,
  dep,
  backtestReturn,
  color,
}: {
  strategy: Strategy;
  dep?: StrategyDeployment;
  backtestReturn?: number;
  color: string;
}) {
  const activate = useStrategiesStore((s) => s.activateStrategy);
  const pause = useStrategiesStore((s) => s.pauseStrategy);
  const pill = pillFor(strategy.status, dep);
  const impl = strategy.templateId ? 'template' : 'dsl';
  const deployed = dep !== undefined;

  // Headline return: realized when deployed, else the latest backtest (tagged `bt`).
  const returnValue = deployed ? dep.returnAll : (backtestReturn ?? null);
  const returnIsBacktest = !deployed && backtestReturn !== undefined;
  const up = returnValue !== null && isUp(returnValue);

  return (
    <Pressable onPress={() => router.push(`/strategy/${strategy.id}`)}>
    <Card shadow>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 9 }}>
        <View style={{ width: 9, height: 30, backgroundColor: color }} />
        <View style={{ flex: 1 }}>
          <Body size={13} style={{ fontWeight: '700' }} numberOfLines={1}>
            {strategy.name}
          </Body>
          <Label style={{ marginTop: 2 }}>
            {impl} · {strategy.timeframe || '1D'} · {strategy.symbols.length} sym
          </Label>
        </View>
        <Badge label={pill.label} variant={pill.variant} />
        <ChevronRight color={palette.gray[400]} size={16} strokeWidth={2} />
      </View>

      <View style={{ flexDirection: 'row', alignItems: 'flex-end', marginTop: 9, gap: 10 }}>
        <View style={{ flexDirection: 'row', gap: 16 }}>
          <View>
            <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 3 }}>
              <Display size={16} color={returnValue === null ? palette.gray[400] : up ? palette.green[500] : palette.red[500]}>
                {returnValue === null ? '—' : pct(returnValue)}
              </Display>
              {returnIsBacktest ? <Mono size={8} color={palette.gray[400]}>bt</Mono> : null}
            </View>
            <Label>Return</Label>
          </View>
          <View>
            <Display size={16}>{deployed ? moneyShort(dep.allocatedCapital) : '—'}</Display>
            <Label>Alloc</Label>
          </View>
        </View>

        {/* Lifecycle toggle */}
        {strategy.status === StrategyStatus.ACTIVE ? (
          <Pressable
            onPress={() => pause(strategy.id)}
            style={{ marginLeft: 'auto', borderWidth: 2, borderColor: palette.ink, paddingHorizontal: 12, paddingVertical: 6 }}
          >
            <Mono size={9} style={{ fontWeight: '700' }}>PAUSE</Mono>
          </Pressable>
        ) : strategy.status === StrategyStatus.PAUSED ? (
          <Pressable
            onPress={() => activate(strategy.id)}
            style={{ marginLeft: 'auto', backgroundColor: palette.orange[500], borderWidth: 2, borderColor: palette.ink, paddingHorizontal: 12, paddingVertical: 6 }}
          >
            <Mono size={9} style={{ fontWeight: '700' }}>ACTIVATE</Mono>
          </Pressable>
        ) : null}
      </View>
    </Card>
    </Pressable>
  );
}

export default function StrategiesScreen() {
  const {
    strategies,
    deployments,
    backtestReturns,
    statusFilter,
    loading,
    error,
    fetchStrategies,
    fetchDeployments,
    fetchBacktestReturns,
    setStatusFilter,
    clearError,
  } = useStrategiesStore();

  useEffect(() => {
    void fetchStrategies();
    void fetchDeployments();
    void fetchBacktestReturns();
  }, [fetchStrategies, fetchDeployments, fetchBacktestReturns]);

  const refresh = () => {
    void fetchStrategies();
    void fetchDeployments();
    void fetchBacktestReturns();
  };

  // Deployment figures are keyed by strategyId; sort deployed strategies (by allocation) first.
  const ordered = [...strategies].sort(
    (a, b) => num(deployments[b.id]?.allocatedCapital) - num(deployments[a.id]?.allocatedCapital),
  );

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: palette.bone }}>
      <View
        style={{
          height: 46,
          borderBottomWidth: 2,
          borderColor: palette.ink,
          backgroundColor: palette.paper,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingHorizontal: 14,
        }}
      >
        <Display size={16}>Strategies</Display>
        <Badge label={String(strategies.length)} />
      </View>

      {loading && strategies.length === 0 ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 }}>
          <ActivityIndicator color={palette.ink} />
          <Label>Loading strategies…</Label>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: 12, gap: 11 }}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={loading} onRefresh={refresh} tintColor={palette.ink} />}
        >
          <View style={{ flexDirection: 'row', gap: 5 }}>
            {FILTERS.map((f) => {
              const on = statusFilter === f.key;
              return (
                <Pressable
                  key={f.key}
                  onPress={() => setStatusFilter(f.key)}
                  style={{ borderWidth: 1.5, borderColor: palette.ink, backgroundColor: on ? palette.ink : palette.paper, paddingHorizontal: 9, paddingVertical: 4 }}
                >
                  <Mono size={9} color={on ? palette.bone : palette.ink}>{f.label}</Mono>
                </Pressable>
              );
            })}
          </View>

          {error ? (
            <Pressable onPress={clearError} style={{ borderWidth: 2, borderColor: palette.red[500], backgroundColor: palette.red[50], padding: 11 }}>
              <Mono size={11} color={palette.red[600]}>{error} · tap to dismiss</Mono>
            </Pressable>
          ) : null}

          {ordered.length === 0 && !loading ? (
            <Card>
              <Label>No strategies{statusFilter !== 'all' ? ` · ${statusFilter}` : ''}</Label>
            </Card>
          ) : (
            ordered.map((s, i) => (
              <StrategyCard
                key={s.id}
                strategy={s}
                dep={deployments[s.id]}
                backtestReturn={backtestReturns[s.id]}
                color={deployments[s.id]?.color || strategyColors[i % strategyColors.length]}
              />
            ))
          )}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}
