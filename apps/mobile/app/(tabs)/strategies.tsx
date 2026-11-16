import { money, num, pct } from '@llamatrade/core/format';
import { ExecutionMode } from '@llamatrade/core/proto/common_pb';
import { StrategyStatus, type Strategy } from '@llamatrade/core/proto/strategy_pb';
import { useStrategiesStore, type StrategyDeployment } from '@llamatrade/core/stores/strategies';
import { router } from 'expo-router';
import { useEffect } from 'react';
import { Alert, View } from 'react-native';

import { makeStyles } from '../../src/theme';
import { Card, EmptyState, Loading, Notice, Pill, Screen, Segmented, StatusMark, Text, pnlTone, type Segment } from '../../src/ui';
import { cadence, runStateOfStrategy } from '../../src/ui/status';

type Filter = 'all' | 'active' | 'paused' | 'draft';

const FILTERS: readonly Segment<Filter>[] = [
  { key: 'all', label: 'All' },
  { key: 'active', label: 'Active' },
  { key: 'paused', label: 'Paused' },
  { key: 'draft', label: 'Draft' },
];

function isFilter(value: string): value is Filter {
  return FILTERS.some((f) => f.key === value);
}

function StrategyCard({
  strategy,
  dep,
  backtestReturn,
}: {
  strategy: Strategy;
  dep?: StrategyDeployment;
  backtestReturn?: number;
}) {
  const s = useStyles();
  const activate = useStrategiesStore((st) => st.activateStrategy);
  const pause = useStrategiesStore((st) => st.pauseStrategy);
  const deployed = dep !== undefined;
  const ret = deployed ? dep.returnAll : (backtestReturn ?? null);
  const live = dep?.mode === ExecutionMode.LIVE;
  const meta = [cadence(strategy.rebalance), deployed ? money(dep.allocatedCapital) : '', live ? 'Live' : '']
    .filter(Boolean)
    .join(' · ');

  const onLongPress = () => {
    if (strategy.status === StrategyStatus.ACTIVE) {
      Alert.alert(strategy.name, 'Pause this strategy? Its session stops placing orders.', [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Pause', onPress: () => pause(strategy.id) },
      ]);
    } else if (strategy.status === StrategyStatus.PAUSED) {
      Alert.alert(strategy.name, 'Resume this strategy on paper?', [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Resume', onPress: () => activate(strategy.id) },
      ]);
    }
  };

  return (
    <Card onPress={() => router.push(`/strategy/${strategy.id}`)} onLongPress={onLongPress} style={s.card}>
      <View style={s.line}>
        <Text variant="subhead" numberOfLines={1} style={s.name}>{strategy.name}</Text>
        <StatusMark state={runStateOfStrategy(strategy.status, dep?.status)} />
      </View>
      <View style={s.line}>
        <Text variant="small" tone="fg3" numberOfLines={1} style={s.name}>
          {meta || `${strategy.symbols.length} symbols`}
        </Text>
        {ret === null ? (
          <Text variant="numStrong" tone="fg3">No runs</Text>
        ) : (
          <View style={s.ret}>
            {!deployed ? <Text variant="caption" tone="fg3">backtest</Text> : null}
            <Text variant="numStrong" tone={pnlTone(ret)}>{pct(ret, 1)}</Text>
          </View>
        )}
      </View>
    </Card>
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
    fetchStrategies();
    fetchDeployments();
    fetchBacktestReturns();
  }, [fetchStrategies, fetchDeployments, fetchBacktestReturns]);

  const refresh = () => {
    fetchStrategies();
    fetchDeployments();
    fetchBacktestReturns();
  };

  const ordered = [...strategies].sort(
    (a, b) => num(deployments[b.id]?.allocatedCapital) - num(deployments[a.id]?.allocatedCapital),
  );
  const filter: Filter = isFilter(statusFilter) ? statusFilter : 'all';

  return (
    <Screen
      title="Strategies"
      right={<Pill label={String(strategies.length)} />}
      refreshing={loading && strategies.length > 0}
      onRefresh={refresh}
    >
      <Segmented options={FILTERS} value={filter} onChange={setStatusFilter} />

      {error ? <Notice title="Couldn't load strategies." detail={`${error} Tap to dismiss.`} onPress={clearError} /> : null}

      {loading && strategies.length === 0 ? (
        <Loading label="Loading strategies" />
      ) : ordered.length === 0 ? (
        filter === 'all' ? (
          <EmptyState
            title="No strategies yet"
            detail="A strategy is a set of rules that decides what to hold. Ask Copilot to draft one, or build one on the web."
          />
        ) : (
          <EmptyState title="Nothing matches" detail={`No ${filter} strategies. Choose All to see every strategy.`} />
        )
      ) : (
        ordered.map((st) => (
          <StrategyCard key={st.id} strategy={st} dep={deployments[st.id]} backtestReturn={backtestReturns[st.id]} />
        ))
      )}
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  card: { gap: 8 },
  line: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  name: { flexShrink: 1 },
  ret: { flexDirection: 'row', alignItems: 'baseline', gap: 6 },
}));
