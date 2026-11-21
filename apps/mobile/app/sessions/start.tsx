import { money } from '@llamatrade/core/format';
import { StrategyStatus } from '@llamatrade/core/proto/strategy_pb';
import { useDeployStore } from '@llamatrade/core/stores/deploy';
import { useFundingStore } from '@llamatrade/core/stores/funding';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { View } from 'react-native';

import { amountProblem, parseAmount, suggestAmount } from '../../src/sessions/amount';
import { AmountField } from '../../src/sessions/AmountField';
import { useSessionRows } from '../../src/sessions/data';
import { ModeTag } from '../../src/sessions/parts';
import { InkButton } from '../../src/sessions/Sheet';
import { makeStyles, radius } from '../../src/theme';
import { Card, ListRow, Loading, Notice, Screen, Text } from '../../src/ui';

const back = { label: 'Back', onPress: () => (router.canGoBack() ? router.back() : router.replace('/sessions')) };

/** Start a strategy on paper (sessions/deploy2 A): the amount, the paper account it joins, Start. */
export default function StartScreen() {
  const s = useStyles();
  const { strategy: strategyId } = useLocalSearchParams<{ strategy?: string }>();
  const { strategies, backtestReturns, loading } = useStrategiesStore();
  const { unallocatedCash, resolved, resolveAccount } = useFundingStore();
  const { deploy, deploying, error: deployError, clearError } = useDeployStore();
  const executions = useTradingStore((st) => st.executions);
  const rows = useSessionRows();
  const [picked, setPicked] = useState<string | null>(strategyId ?? null);
  const [text, setText] = useState('');
  const [touched, setTouched] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);

  useEffect(() => {
    const st = useStrategiesStore.getState();
    if (st.strategies.length === 0) st.fetchStrategies().catch(() => undefined);
    if (Object.keys(st.backtestReturns).length === 0) st.fetchBacktestReturns().catch(() => undefined);
    resolveAccount().catch(() => undefined);
    clearError();
  }, [resolveAccount, clearError]);

  useEffect(() => {
    if (resolved && text === '' && unallocatedCash > 0) setText(String(suggestAmount(unallocatedCash)));
  }, [resolved, unallocatedCash, text]);

  const strategy = strategies.find((x) => x.id === picked);
  const runningIds = useMemo(() => new Set(rows.filter((r) => r.state !== 'stopped').map((r) => r.strategyId)), [rows]);
  const everRun = useMemo(() => new Set(executions.map((e) => e.strategyId)), [executions]);
  const paper = rows.filter((r) => r.mode === 'paper' && r.state !== 'stopped');
  const amount = parseAmount(text);
  const problem = amountProblem(amount, resolved ? unallocatedCash : null);
  const backtest = strategy ? backtestReturns[strategy.id] : undefined;

  const start = async () => {
    setTouched(true);
    if (!strategy || problem || amount === null) return;
    const res = await deploy({ strategyId: strategy.id, strategyName: strategy.name, allocation: amount, goLive: true, mode: 'paper' });
    if (!res) return;
    useTradingStore.getState().loadBlotter().catch(() => undefined);
    if (res.liveError) {
      setLiveError(res.liveError);
      return;
    }
    if (res.sessionId) router.replace({ pathname: '/sessions/[id]', params: { id: res.sessionId } });
    else router.replace('/sessions');
  };

  if (!strategy) {
    const choices = strategies.filter((x) => x.status !== StrategyStatus.ARCHIVED);
    return (
      <Screen title="Start on paper" back={back} art="bold" artSeed="sessions-start-pick">
        <Text variant="small" tone="fg2" style={s.subtitle}>Pick the strategy to run. It trades your Alpaca paper account.</Text>
        {loading && choices.length === 0 ? (
          <Loading label="Loading strategies" />
        ) : (
          <Card style={s.list}>
            {choices.map((x, i) => {
              const running = runningIds.has(x.id);
              const ret = backtestReturns[x.id];
              const sub = running
                ? 'Already running'
                : [
                    `Version ${x.version}`,
                    ret !== undefined ? `backtest ${ret >= 0 ? '+' : '−'}${Math.abs(ret).toFixed(1)}%` : 'not backtested',
                    everRun.has(x.id) ? '' : 'never run',
                  ]
                    .filter(Boolean)
                    .join(' · ');
              return <ListRow key={x.id} label={x.name} sub={sub} last={i === choices.length - 1} onPress={() => setPicked(x.id)} />;
            })}
          </Card>
        )}
      </Screen>
    );
  }

  return (
    <Screen
      title={`Start ${strategy.name}`}
      back={strategyId ? back : { label: 'Strategies', onPress: () => setPicked(null) }}
      art="bold"
      artSeed={`sessions-start-${strategy.id}`}
      eyebrow={
        <View style={s.eyebrow}>
          <ModeTag mode="paper" />
          <Text variant="small" tone="fg3">Version {strategy.version}</Text>
        </View>
      }
    >
      <AmountField
        label="Amount to start with"
        value={text}
        onChange={(v) => {
          setText(v);
          setTouched(true);
        }}
        available={resolved ? unallocatedCash : null}
        error={touched ? problem : null}
      />

      <Card style={s.list}>
        <View style={s.cardHead}>
          <Text variant="smallStrong">On the paper account</Text>
          <Text variant="small" tone="fg3">{paper.length === 1 ? '1 running' : `${paper.length} running`}</Text>
        </View>
        {paper.map((r) => (
          <ListRow key={r.id} label={r.title} value={<Text variant="num" tone="fg2">{r.value !== null ? money(r.value, 2) : '–'}</Text>} />
        ))}
        <ListRow
          last
          label={<Text variant="bodyStrong" tone="accent">{strategy.name}</Text>}
          sub="New, starts now"
          value={<Text variant="num" tone="accent">{amount !== null ? money(amount, 2) : '–'}</Text>}
        />
      </Card>

      <Card style={s.list}>
        <ListRow label="First orders" sub="Placed by the strategy on its own schedule. The date isn't in the app yet." />
        <ListRow last label="Until then" sub={`${amount !== null ? money(amount, 2) : 'The amount'} waits as cash in its own sleeve.`} />
      </Card>

      <Text variant="small" tone="fg3">
        {backtest !== undefined
          ? `Latest backtest: ${backtest >= 0 ? '+' : '−'}${Math.abs(backtest).toFixed(1)}% total return. A backtest is a simulation on past prices.`
          : 'This strategy has no completed backtest.'}
        {everRun.has(strategy.id) ? '' : ' It has never run on paper or live.'}
      </Text>

      {deployError ? <Notice title="It didn't start." detail={deployError} /> : null}
      {liveError ? <Notice title="The sleeve is funded, but the paper session didn't start." detail={liveError} /> : null}
      {runningIds.has(strategy.id) ? <Notice tone="neutral" detail="This strategy already has a running session. Starting it again opens a second one." /> : null}

      <InkButton label="Start on paper" onPress={start} loading={deploying} disabled={!resolved} />
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  subtitle: { marginTop: -8 },
  eyebrow: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  list: { paddingVertical: 2, borderRadius: radius.lg },
  cardHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingTop: 10, paddingBottom: 4 },
}));
