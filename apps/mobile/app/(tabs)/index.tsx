import { router } from 'expo-router';
import { Sparkles, TrendingUp, Zap } from 'lucide-react-native';
import { isUp, money, num, pct, signedMoney, toMs } from '@llamatrade/core/format';
import { MarketStatus } from '@llamatrade/core/proto/market_data_pb';
import { TransactionType, type Transaction } from '@llamatrade/core/proto/portfolio_pb';
import { useEffect } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { LineChart } from '../../src/charts/LineChart';
import { useAuthStore } from '../../src/stores/auth';
import { usePortfolioStore } from '../../src/stores/portfolio';
import { palette } from '../../src/theme';
import { Badge, Body, Card, Display, Label, Mono } from '../../src/ui';

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 18 ? 'Good afternoon' : 'Good evening';
}

function today(): string {
  return new Date().toLocaleDateString('en-US', { weekday: 'short', month: 'short', day: 'numeric' });
}

function marketBadge(status: MarketStatus | null): { label: string; variant: 'green' | 'gray' | 'orange' } {
  switch (status) {
    case MarketStatus.OPEN:
      return { label: 'Market Open', variant: 'green' };
    case MarketStatus.PRE_MARKET:
      return { label: 'Pre-Market', variant: 'orange' };
    case MarketStatus.AFTER_HOURS:
      return { label: 'After Hours', variant: 'orange' };
    case MarketStatus.CLOSED:
      return { label: 'Market Closed', variant: 'gray' };
    default:
      return { label: 'Paper', variant: 'orange' };
  }
}

const TXN: Partial<Record<TransactionType, { tag: string; color: string }>> = {
  [TransactionType.BUY]: { tag: 'BUY', color: palette.green[500] },
  [TransactionType.SELL]: { tag: 'SELL', color: palette.red[500] },
  [TransactionType.DIVIDEND]: { tag: 'DIV', color: palette.blue[500] },
  [TransactionType.DEPOSIT]: { tag: 'DEP', color: palette.ink },
  [TransactionType.WITHDRAWAL]: { tag: 'WD', color: palette.ink },
  [TransactionType.FEE]: { tag: 'FEE', color: palette.gray[500] },
  [TransactionType.INTEREST]: { tag: 'INT', color: palette.blue[500] },
};

function relTime(ms: number): string {
  if (!ms) return '';
  const m = Math.floor((Date.now() - ms) / 60000);
  if (m < 1) return 'now';
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d`;
  return new Date(ms).toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

function txnRow(t: Transaction): { tag: string; color: string; title: string; sub: string; when: string } {
  const meta = TXN[t.type] ?? { tag: 'TXN', color: palette.gray[500] };
  const qty = num(t.quantity);
  const sub =
    (t.type === TransactionType.BUY || t.type === TransactionType.SELL) && qty
      ? `${qty} ${t.symbol} @ ${money(t.price)}`
      : money(t.amount) + (t.symbol ? ` · ${t.symbol}` : '');
  return {
    tag: meta.tag,
    color: meta.color,
    title: t.description || `${meta.tag} ${t.symbol}`.trim(),
    sub: sub || money(t.amount),
    when: relTime(toMs(t.timestamp)),
  };
}

export default function HomeScreen() {
  const user = useAuthStore((s) => s.user);
  const { portfolio, equityCurve, benchmarkCurve, transactions, marketStatus, loading, refreshing, loaded, error, fetch } =
    usePortfolioStore();

  useEffect(() => {
    void fetch();
  }, [fetch]);

  const firstName = user?.firstName || (user?.email ?? '').split('@')[0] || 'there';
  const market = marketBadge(marketStatus);

  const equity = equityCurve;
  const bench = benchmarkCurve.length > 1 ? benchmarkCurve : undefined;

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
        <Display size={16}>Home</Display>
        <Badge label={market.label} variant={market.variant} />
      </View>

      {loading && !loaded ? (
        <View style={{ flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10 }}>
          <ActivityIndicator color={palette.ink} />
          <Label>Loading…</Label>
        </View>
      ) : (
        <ScrollView
          contentContainerStyle={{ padding: 12, gap: 11 }}
          showsVerticalScrollIndicator={false}
          refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void fetch({ refresh: true })} tintColor={palette.ink} />}
        >
          <View>
            <Display size={22}>
              {greeting()}, {firstName}.
            </Display>
            <Label style={{ marginTop: 4 }}>
              {today()} · {loaded ? 'machine running' : '—'}
            </Label>
          </View>

          {error ? (
            <Pressable onPress={() => void fetch()} style={{ borderWidth: 2, borderColor: palette.red[500], backgroundColor: palette.red[50], padding: 11 }}>
              <Mono size={11} color={palette.red[600]}>{error} · tap to retry</Mono>
            </Pressable>
          ) : null}

          {portfolio ? (
            <>
              {/* Today hero — the day's move is the headline (Book owns total equity) */}
              <Card ink shadow>
                <Label color="#b7b0a2">Today · Paper</Label>
                <Display size={30} color={palette.bone} style={{ marginTop: 4 }}>
                  {signedMoney(portfolio.dayReturn)}
                </Display>
                <View style={{ flexDirection: 'row', gap: 6, marginTop: 8, flexWrap: 'wrap' }}>
                  <Badge label={`${pct(portfolio.dayReturnPercent)} TODAY`} variant={isUp(portfolio.dayReturn) ? 'green' : 'red'} />
                  <Badge label={`EQUITY ${money(portfolio.totalValue)}`} variant="orange" />
                </View>
                {equity.length > 1 ? (
                  <View style={{ marginTop: 10 }}>
                    <LineChart values={equity} benchmark={bench} height={44} fill="rgba(255,77,28,0.22)" />
                  </View>
                ) : null}
              </Card>

              {/* Quick actions — Home is the daily jump-off point */}
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <Pressable
                  onPress={() => router.push('/copilot')}
                  style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.orange[500], paddingVertical: 12 }}
                >
                  <Sparkles color={palette.ink} size={13} strokeWidth={2.5} />
                  <Mono size={10.5} style={{ fontWeight: '700' }}>COPILOT</Mono>
                </Pressable>
                <Pressable
                  onPress={() => router.push('/strategies')}
                  style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.paper, paddingVertical: 12 }}
                >
                  <TrendingUp color={palette.ink} size={13} strokeWidth={2.5} />
                  <Mono size={10.5} style={{ fontWeight: '700' }}>STRATS</Mono>
                </Pressable>
                <Pressable
                  onPress={() => router.push('/account/connect-broker')}
                  style={{ flex: 1, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 5, borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.paper, paddingVertical: 12 }}
                >
                  <Zap color={palette.ink} size={13} strokeWidth={2.5} />
                  <Mono size={10.5} style={{ fontWeight: '700' }}>GO LIVE</Mono>
                </Pressable>
              </View>

              {/* Recent activity — Home owns "what just happened" */}
              {transactions.length ? (
                <>
                  <Label style={{ marginTop: 2 }}>Recent Activity</Label>
                  <Card>
                    {transactions.slice(0, 6).map((t, i) => {
                      const r = txnRow(t);
                      const last = i === Math.min(6, transactions.length) - 1;
                      return (
                        <View
                          key={t.id || i}
                          style={{ flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 7, borderBottomWidth: last ? 0 : 1, borderColor: 'rgba(13,13,13,0.12)' }}
                        >
                          <View style={{ backgroundColor: r.color, paddingHorizontal: 5, paddingVertical: 2 }}>
                            <Mono size={8} color={palette.bone}>{r.tag}</Mono>
                          </View>
                          <View style={{ flex: 1 }}>
                            <Body size={11.5} style={{ fontWeight: '600' }} numberOfLines={1}>{r.title}</Body>
                            <Mono size={9} color={palette.gray[500]} numberOfLines={1}>{r.sub}</Mono>
                          </View>
                          <Mono size={9} color={palette.gray[500]}>{r.when}</Mono>
                        </View>
                      );
                    })}
                  </Card>
                </>
              ) : null}
            </>
          ) : !error && loaded ? (
            <Card><Label>No portfolio found for this account</Label></Card>
          ) : null}
        </ScrollView>
      )}
    </SafeAreaView>
  );
}
