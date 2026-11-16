import { money, num, pct, qty, signedMoney } from '@llamatrade/core/format';
import { ExecutionMode, ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { router } from 'expo-router';
import { useEffect, useMemo } from 'react';
import { View } from 'react-native';

import { usePortfolioStore } from '../../src/stores/portfolio';
import { makeStyles } from '../../src/theme';
import { Card, ListRow, Loading, Notice, PanelError, Pill, Screen, StatusMark, Text, WeightStrip, pnlTone } from '../../src/ui';
import { runStateOfExecution } from '../../src/ui/status';

export default function PortfolioScreen() {
  const s = useStyles();
  const { portfolio, strategies, positions, loading, refreshing, loaded, error, fetch } = usePortfolioStore();

  useEffect(() => {
    fetch();
  }, [fetch]);

  const holdings = useMemo(() => {
    const bySymbol = new Map<string, { symbol: string; value: number; pnl: number; shares: number }>();
    for (const p of positions) {
      const value = num(p.marketValue) || num(p.quantity) * num(p.currentPrice);
      if (value <= 0) continue;
      const row = bySymbol.get(p.symbol) ?? { symbol: p.symbol, value: 0, pnl: 0, shares: 0 };
      row.value += value;
      row.pnl += num(p.unrealizedPnl);
      row.shares += num(p.quantity);
      bySymbol.set(p.symbol, row);
    }
    const rows = [...bySymbol.values()].sort((a, b) => b.value - a.value);
    const total = rows.reduce((sum, r) => sum + r.value, 0);
    return rows.map((r) => ({ ...r, weight: total > 0 ? (r.value / total) * 100 : 0 }));
  }, [positions]);

  const sleeves = useMemo(
    () => [...strategies].sort((a, b) => num(b.currentValue) - num(a.currentValue)),
    [strategies],
  );
  const failing = sleeves.filter((x) => x.status === ExecutionStatus.ERROR);
  const total = num(portfolio?.totalValue);
  const allocated = sleeves.reduce((sum, x) => sum + num(x.currentValue), 0);
  const unallocated = Math.max(0, total - allocated);
  const lifetime = num(portfolio?.totalReturn);

  return (
    <Screen
      title="Portfolio"
      right={<Pill label="Paper" dot />}
      refreshing={refreshing}
      onRefresh={() => fetch({ refresh: true })}
    >
      {loading && !loaded ? (
        <Loading label="Loading portfolio" />
      ) : error && !portfolio ? (
        <PanelError title="Couldn't load the portfolio" detail={error} onRetry={() => fetch()} />
      ) : portfolio ? (
        <>
          {error ? <Notice title="Couldn't refresh." detail={`${error} Pull down to try again.`} /> : null}

          <Card style={s.equity}>
            <Text variant="label" tone="fg3">Total equity</Text>
            <Text variant="hero" style={s.equityFigure}>{money(portfolio.totalValue, 2)}</Text>
            <Text variant="numSmall" tone={pnlTone(lifetime)}>
              {signedMoney(lifetime, 2)} ({pct(portfolio.totalReturnPercent)}) since start
            </Text>
            {total > 0 ? (
              <View style={s.strip}>
                <WeightStrip weights={[...sleeves.map((x) => num(x.currentValue)), unallocated]} />
              </View>
            ) : null}
          </Card>

          {failing.map((x) => (
            <Notice
              key={x.executionId}
              title={`${x.strategyName} stopped with an error.`}
              detail="Its sleeve keeps its positions until you restart or stop it."
              onPress={() => router.push(`/strategy/${x.strategyId}`)}
            />
          ))}

          <Card style={s.listCard}>
            {sleeves.map((x) => {
              const pnl = num(x.currentValue) - num(x.allocatedCapital);
              const live = x.mode === ExecutionMode.LIVE;
              return (
                <ListRow
                  key={x.executionId}
                  onPress={() => router.push(`/strategy/${x.strategyId}`)}
                  label={<Text variant="bodyStrong" numberOfLines={1}>{x.strategyName}</Text>}
                  sub={
                    <StatusMark
                      state={runStateOfExecution(x.status)}
                      label={live ? `${runLabel(x.status)} · live` : undefined}
                    />
                  }
                  right={
                    <View style={s.figures}>
                      <Text variant="numStrong">{money(x.currentValue, 2)}</Text>
                      <Text variant="numSmall" tone={pnlTone(pnl)}>{signedMoney(pnl, 2)}</Text>
                    </View>
                  }
                />
              );
            })}
            <ListRow
              last
              label={<Text variant="body" tone="fg2">Unallocated</Text>}
              right={<Text variant="numStrong" tone="fg2">{money(unallocated, 2)}</Text>}
            />
          </Card>

          {holdings.length ? (
            <Card style={s.listCard}>
              <Text variant="label" tone="fg3" style={s.cardLabel}>Holdings · {holdings.length}</Text>
              {holdings.map((h, i) => (
                <ListRow
                  key={h.symbol}
                  last={i === holdings.length - 1}
                  label={<Text variant="numStrong">{h.symbol}</Text>}
                  sub={<Text variant="numSmall" tone="fg3">{h.weight.toFixed(1)}% · {qty(h.shares)} sh</Text>}
                  right={
                    <View style={s.figures}>
                      <Text variant="num">{money(h.value, 2)}</Text>
                      <Text variant="numSmall" tone={pnlTone(h.pnl)}>{signedMoney(h.pnl, 2)}</Text>
                    </View>
                  }
                />
              ))}
            </Card>
          ) : null}
        </>
      ) : loaded ? (
        <PanelError title="No portfolio yet" detail="This account has no paper portfolio. Connect Alpaca paper keys to start." />
      ) : null}
    </Screen>
  );
}

function runLabel(status: ExecutionStatus): string {
  const state = runStateOfExecution(status);
  return state.charAt(0).toUpperCase() + state.slice(1);
}

const useStyles = makeStyles(() => ({
  equity: { gap: 4 },
  equityFigure: { marginTop: 2 },
  strip: { marginTop: 10 },
  listCard: { paddingVertical: 4 },
  cardLabel: { marginTop: 10, marginBottom: 2 },
  figures: { alignItems: 'flex-end', gap: 2 },
}));
