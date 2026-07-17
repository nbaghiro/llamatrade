import { router } from 'expo-router';
import { ChevronRight } from 'lucide-react-native';
import { useEffect, useMemo } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ExecutionMode, ExecutionStatus } from '@llamatrade/core/proto/common_pb';
import { isUp, money, num, pct, qty, signedMoney } from '@llamatrade/core/format';
import { LineChart } from '../../src/charts/LineChart';
import { useAuthStore } from '../../src/stores/auth';
import { usePortfolioStore } from '../../src/stores/portfolio';
import { palette, strategyColors } from '../../src/theme';
import { Badge, Body, Card, Display, KpiTile, Label, Mono } from '../../src/ui';

const STATUS_LABEL: Record<number, string> = {
  [ExecutionStatus.PENDING]: 'Pending',
  [ExecutionStatus.RUNNING]: 'Running',
  [ExecutionStatus.PAUSED]: 'Paused',
  [ExecutionStatus.STOPPED]: 'Stopped',
  [ExecutionStatus.ERROR]: 'Error',
};

export default function PortfolioScreen() {
  const user = useAuthStore((s) => s.user);
  const { portfolio, strategies, positions, equityCurve, benchmarkCurve, loading, refreshing, loaded, error, fetch } =
    usePortfolioStore();

  useEffect(() => {
    void fetch();
  }, [fetch]);

  const holder = user ? `${user.firstName ?? ''} ${user.lastName ?? ''}`.trim() || user.email : '—';

  // Account holdings: real open positions aggregated per symbol, largest first.
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

  const openPositions = holdings.length || strategies.reduce((n, s) => n + s.positionsCount, 0);

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
        <Display size={16}>Portfolio</Display>
        <Badge label="Paper" variant="orange" />
      </View>

      {/* First load */}
      {loading && !loaded ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 }}>
          <ActivityIndicator color={palette.ink} />
          <Label>Loading portfolio…</Label>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: 12, gap: 11 }}
          showsVerticalScrollIndicator={false}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => fetch({ refresh: true })}
              tintColor={palette.ink}
            />
          }
        >
          {error ? (
            <View
              style={{
                borderWidth: 2,
                borderColor: palette.red[500],
                backgroundColor: palette.red[50],
                padding: 11,
                gap: 8,
              }}
            >
              <Mono size={11} color={palette.red[600]}>
                {error}
              </Mono>
              <Pressable
                onPress={() => fetch()}
                style={{
                  alignSelf: 'flex-start',
                  borderWidth: 2,
                  borderColor: palette.ink,
                  backgroundColor: palette.paper,
                  paddingHorizontal: 12,
                  paddingVertical: 6,
                }}
              >
                <Mono size={10} style={{ fontWeight: '700' }}>
                  RETRY
                </Mono>
              </Pressable>
            </View>
          ) : null}

          {portfolio ? (
            <>
              <View style={{ flexDirection: 'row', gap: 6, flexWrap: 'wrap' }}>
                <Badge label={holder} />
                <Badge label={`#${portfolio.id.slice(0, 6).toUpperCase()}`} />
                <Badge label={`${openPositions} positions`} />
              </View>

              <Card ink shadow>
                <Label color="#b7b0a2">Total Equity</Label>
                <Display size={30} color={palette.bone} style={{ marginTop: 4 }}>
                  {money(portfolio.totalValue)}
                </Display>
                <Label color="#b7b0a2" style={{ marginTop: 6 }}>
                  ↗ {signedMoney(portfolio.totalReturn)} lifetime · {pct(portfolio.totalReturnPercent)}
                </Label>
                {equityCurve.length > 1 ? (
                  <View style={{ marginTop: 10 }}>
                    <LineChart
                      values={equityCurve}
                      benchmark={benchmarkCurve.length > 1 ? benchmarkCurve : undefined}
                      height={64}
                      color={palette.orange[500]}
                      fill="rgba(255,77,28,0.24)"
                    />
                  </View>
                ) : null}
              </Card>

              <View style={{ flexDirection: 'row', gap: 8 }}>
                <KpiTile
                  value={signedMoney(portfolio.dayReturn)}
                  label={`Day P&L · ${pct(portfolio.dayReturnPercent)}`}
                  tone={isUp(portfolio.dayReturn) ? 'up' : 'down'}
                />
                <KpiTile
                  value={pct(portfolio.totalReturnPercent)}
                  label="Total Return"
                  tone={isUp(portfolio.totalReturnPercent) ? 'up' : 'down'}
                />
              </View>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <KpiTile value={money(portfolio.cashBalance)} label="Free Cash" />
                <KpiTile value={money(portfolio.positionsValue)} label="Deployed" />
              </View>

              {/* Holdings — per-symbol book, the ledger this screen is named for */}
              {holdings.length > 0 ? (
                <>
                  <Label style={{ marginTop: 2 }}>Holdings · {holdings.length}</Label>
                  <View style={{ flexDirection: 'row', height: 12, borderWidth: 2, borderColor: palette.ink }}>
                    {holdings.map((h, i) => (
                      <View
                        key={h.symbol}
                        style={{ flex: h.weight, backgroundColor: strategyColors[i % strategyColors.length] }}
                      />
                    ))}
                  </View>
                  <Card>
                    {holdings.map((h, i) => {
                      const up = h.pnl >= 0;
                      const last = i === holdings.length - 1;
                      return (
                        <View
                          key={h.symbol}
                          style={{
                            flexDirection: 'row',
                            alignItems: 'center',
                            gap: 9,
                            paddingVertical: 8,
                            borderBottomWidth: last ? 0 : 1,
                            borderColor: 'rgba(13,13,13,0.12)',
                          }}
                        >
                          <View style={{ width: 9, height: 26, backgroundColor: strategyColors[i % strategyColors.length] }} />
                          <View style={{ flex: 1 }}>
                            <Body size={13} style={{ fontWeight: '700' }}>
                              {h.symbol}
                            </Body>
                            <Mono size={9} color={palette.gray[500]}>
                              {h.weight.toFixed(1)}% · {qty(h.shares)} sh
                            </Mono>
                          </View>
                          <View style={{ alignItems: 'flex-end' }}>
                            <Mono size={11} style={{ fontWeight: '700' }}>
                              {money(h.value)}
                            </Mono>
                            <Mono size={9} color={up ? palette.green[600] : palette.red[600]}>
                              {signedMoney(h.pnl)}
                            </Mono>
                          </View>
                        </View>
                      );
                    })}
                  </Card>
                </>
              ) : null}

              <Label style={{ marginTop: 2 }}>Strategies · {strategies.length}</Label>
              {strategies.length === 0 ? (
                <Card>
                  <Label>No deployed strategies yet</Label>
                </Card>
              ) : (
                strategies.map((s, i) => {
                  const ret = s.returns?.returnAll;
                  const up = isUp(ret);
                  const pnl = num(s.currentValue) - num(s.allocatedCapital);
                  return (
                    <Pressable key={s.executionId} onPress={() => router.push(`/strategy/${s.strategyId}`)}>
                    <Card>
                      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 9 }}>
                        <View
                          style={{
                            width: 9,
                            height: 34,
                            backgroundColor: s.color || strategyColors[i % strategyColors.length],
                          }}
                        />
                        <View style={{ flex: 1 }}>
                          <Body size={13} style={{ fontWeight: '700' }} numberOfLines={1}>
                            {s.strategyName}
                          </Body>
                          <Label style={{ marginTop: 2 }}>
                            {s.mode === ExecutionMode.LIVE ? 'live' : 'paper'} ·{' '}
                            {STATUS_LABEL[s.status] ?? '—'} · {s.positionsCount} pos
                          </Label>
                        </View>
                        <View style={{ alignItems: 'flex-end' }}>
                          <Display size={15} color={up ? palette.green[500] : palette.red[500]}>
                            {pct(ret)}
                          </Display>
                          <Mono size={9} color={palette.gray[500]}>
                            {signedMoney(pnl)}
                          </Mono>
                        </View>
                        <ChevronRight color={palette.gray[400]} size={15} strokeWidth={2} />
                      </View>
                      <View
                        style={{
                          flexDirection: 'row',
                          justifyContent: 'space-between',
                          marginTop: 8,
                          paddingTop: 8,
                          borderTopWidth: 1,
                          borderColor: 'rgba(13,13,13,0.12)',
                        }}
                      >
                        <Mono size={10} color={palette.gray[500]}>
                          allocated {money(s.allocatedCapital)}
                        </Mono>
                        <Mono size={10}>{money(s.currentValue)}</Mono>
                      </View>
                    </Card>
                    </Pressable>
                  );
                })
              )}
            </>
          ) : !error && loaded ? (
            <Card>
              <Label>No portfolio found for this account</Label>
            </Card>
          ) : null}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}
