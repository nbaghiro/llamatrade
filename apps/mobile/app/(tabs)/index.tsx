import { money, num, pct, signedMoney, timeAgo, toDate } from '@llamatrade/core/format';
import { ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { MarketStatus } from '@llamatrade/core/proto/market_data_pb';
import { TransactionType, type Transaction } from '@llamatrade/core/proto/portfolio_pb';
import { router } from 'expo-router';
import { useEffect } from 'react';
import { View } from 'react-native';

import { LineChart } from '../../src/charts/LineChart';
import { timeLabels } from '../../src/charts/paths';
import { usePortfolioStore } from '../../src/stores/portfolio';
import { makeStyles, radius } from '../../src/theme';
import { Button, Card, Loading, Notice, PanelError, Screen, StatusMark, Text, pnlTone, type RunState } from '../../src/ui';

function marketState(status: MarketStatus | null): { state: RunState; label: string } | null {
  switch (status) {
    case MarketStatus.OPEN:
      return { state: 'running', label: 'Market open' };
    case MarketStatus.PRE_MARKET:
      return { state: 'stopped', label: 'Pre-market' };
    case MarketStatus.AFTER_HOURS:
      return { state: 'stopped', label: 'After hours' };
    case MarketStatus.CLOSED:
      return { state: 'stopped', label: 'Market closed' };
    default:
      return null;
  }
}

const TXN_TAG: Partial<Record<TransactionType, string>> = {
  [TransactionType.BUY]: 'BUY',
  [TransactionType.SELL]: 'SELL',
  [TransactionType.DIVIDEND]: 'DIV',
  [TransactionType.DEPOSIT]: 'DEP',
  [TransactionType.WITHDRAWAL]: 'WD',
  [TransactionType.FEE]: 'FEE',
  [TransactionType.INTEREST]: 'INT',
};

function txnRow(t: Transaction): { tag: string; title: string; when: string } {
  const tag = TXN_TAG[t.type] ?? 'TXN';
  const shares = num(t.quantity);
  const trade = (t.type === TransactionType.BUY || t.type === TransactionType.SELL) && shares;
  const title = trade
    ? `${shares} ${t.symbol} at ${money(t.price, 2)}`
    : t.description || `${money(t.amount, 2)}${t.symbol ? ` · ${t.symbol}` : ''}`;
  return { tag, title, when: timeAgo(toDate(t.timestamp)) };
}

export default function HomeScreen() {
  const s = useStyles();
  const {
    portfolio,
    strategies,
    equityCurve,
    equityTimes,
    benchmarkCurve,
    transactions,
    marketStatus,
    loading,
    refreshing,
    loaded,
    error,
    fetch,
  } = usePortfolioStore();

  useEffect(() => {
    fetch();
  }, [fetch]);

  const market = marketState(marketStatus);
  const failing = strategies.filter((x) => x.status === ExecutionStatus.ERROR);
  const day = num(portfolio?.dayReturn);

  return (
    <Screen refreshing={refreshing} onRefresh={() => fetch({ refresh: true })}>
      <View style={s.top}>
        <Text variant="label" tone="fg3">Today · Paper</Text>
        {market ? <StatusMark state={market.state} label={market.label} /> : null}
      </View>
      {loading && !loaded ? (
        <Loading label="Loading your account" />
      ) : error && !portfolio ? (
        <PanelError title="Couldn't load your account" detail={error} onRetry={() => fetch()} />
      ) : portfolio ? (
        <>
          {error ? <Notice title="Couldn't refresh." detail={`${error} Pull down to try again.`} /> : null}
          {failing.length ? (
            <Notice
              title={failing.length === 1 ? `${failing[0].strategyName} stopped with an error.` : `${failing.length} sessions stopped with an error.`}
              detail="Open Portfolio to see which."
              onPress={() => router.push('/portfolio')}
            />
          ) : null}

          <View style={s.hero}>
            <Text variant="hero">{money(portfolio.totalValue, 2)}</Text>
            <Text variant="numStrong" tone={pnlTone(day)}>
              {signedMoney(day, 2)} ({pct(portfolio.dayReturnPercent)})
            </Text>
          </View>

          {equityCurve.length > 1 ? (
            <Card style={s.chartCard}>
              <LineChart
                values={equityCurve}
                benchmark={benchmarkCurve.length > 1 ? benchmarkCurve : undefined}
                height={130}
                axis
                xLabels={timeLabels(equityTimes)}
              />
            </Card>
          ) : null}

          <View style={s.actions}>
            <Button label="Copilot" variant="secondary" onPress={() => router.push('/copilot')} style={s.action} />
            <Button label="Strategies" variant="secondary" onPress={() => router.push('/strategies')} style={s.action} />
            <Button label="Connect" variant="secondary" onPress={() => router.push('/account/connect-broker')} style={s.action} />
          </View>

          {transactions.length ? (
            <Card>
              <Text variant="label" tone="fg3" style={s.cardLabel}>Recent activity</Text>
              {transactions.slice(0, 6).map((t, i, list) => {
                const r = txnRow(t);
                return (
                  <View key={t.id || i} style={[s.txn, i < list.length - 1 ? s.txnDivider : null]}>
                    <View style={s.tag}>
                      <Text variant="numSmall" tone="fg2" style={s.tagText}>{r.tag}</Text>
                    </View>
                    <Text variant="small" style={s.txnTitle} numberOfLines={1}>{r.title}</Text>
                    <Text variant="numSmall" tone="fg3">{r.when}</Text>
                  </View>
                );
              })}
            </Card>
          ) : null}
        </>
      ) : loaded ? (
        <PanelError title="No portfolio yet" detail="This account has no paper portfolio. Connect Alpaca paper keys to start." />
      ) : null}
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  top: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', minHeight: 22 },
  hero: { gap: 4, marginTop: -6 },
  chartCard: { paddingHorizontal: 12, paddingVertical: 12 },
  actions: { flexDirection: 'row', gap: 8 },
  action: { flex: 1, paddingHorizontal: 6 },
  cardLabel: { marginBottom: 4 },
  txn: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 9 },
  txnDivider: { borderBottomWidth: 1, borderColor: t.c.line },
  tag: {
    minWidth: 38,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: t.c.lineStrong,
    borderRadius: radius.xs,
    paddingHorizontal: 4,
    paddingVertical: 1,
  },
  tagText: { fontSize: 10.5, lineHeight: 14 },
  txnTitle: { flex: 1 },
}));
