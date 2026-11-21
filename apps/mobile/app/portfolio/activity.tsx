import { money, signedMoney } from '@llamatrade/core/format';
import { useActivityStore } from '@llamatrade/core/stores/activity';
import { usePortfolioStore } from '@llamatrade/core/stores/portfolio';
import { router } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { View } from 'react-native';

import { Lanes, type Lane } from '../../src/charts/Lanes';
import { laneCode } from '../../src/charts/scale';
import { displayName } from '../../src/home/model';
import { PaperAmount } from '../../src/home/PaperAmount';
import { dayLabel, hm } from '../../src/home/when';
import { dayCounts, groupByDay, statementTag, type StatementIn } from '../../src/portfolio/model';
import { makeStyles, radius } from '../../src/theme';
import { Button, Card, EmptyState, Loading, PanelError, Screen, Segmented, Text } from '../../src/ui';

type Range = '1M' | '3M' | 'All';
const DAY = 86_400_000;
const SPAN: Record<Range, number | null> = { '1M': 31 * DAY, '3M': 92 * DAY, All: null };

/** Activity (activity2 A): a lane per sleeve above the statement, with a range filter. */
export default function ActivityScreen() {
  const s = useStyles();
  const { rows, loading, loadingMore, error, hasMore, fetch, loadMore } = useActivityStore();
  const sleeves = usePortfolioStore((st) => st.sleeves);
  const [range, setRange] = useState<Range>('1M');

  useEffect(() => {
    fetch();
    if (usePortfolioStore.getState().sleeves.length === 0) usePortfolioStore.getState().fetchPortfolio();
  }, [fetch]);

  const now = Date.now();
  const from = SPAN[range] === null ? Math.min(now - 7 * DAY, ...rows.map((r) => r.at.getTime())) : now - (SPAN[range] ?? 0);
  const statement: StatementIn[] = useMemo(
    () =>
      rows
        .filter((r) => r.at.getTime() >= from)
        .map((r) => ({
          id: r.id,
          kind: r.kind,
          label: r.label,
          sublabel: r.sublabel,
          signed: r.signed,
          amount: r.amount,
          t: r.at.getTime(),
          account: r.account,
          sleeveId: r.sleeveId,
        })),
    [rows, from],
  );
  const days = useMemo(() => groupByDay(statement), [statement]);
  const counts = useMemo(() => dayCounts(statement), [statement]);
  const nameOf = (sleeveId: string) => {
    const sl = sleeves.find((x) => x.sleeveId === sleeveId);
    return sl ? displayName(sl.name) : sleeveId === 'cash' ? 'Cash' : 'Other';
  };
  const lanes: Lane[] = [...counts.entries()].map(([key, list]) => {
    const sl = sleeves.find((x) => x.sleeveId === key);
    return {
      key,
      label: key === 'cash' ? '$' : laneCode(nameOf(key)),
      tone: sl?.frozen ? 'risk' : sl?.live ? 'ink' : key === 'cash' ? 'muted' : 'accent',
      dashed: !sl?.live,
      markers: list.map((d) => ({ t: d.day + DAY / 2, kind: 'fill' as const, count: d.count, id: String(d.day) })),
    };
  });

  return (
    <Screen
      title="Activity"
      artSeed="portfolio-activity-lanes"
      art="bold"
      back={{ label: 'Portfolio', onPress: () => (router.canGoBack() ? router.back() : router.replace('/portfolio')) }}
      refreshing={loading && rows.length > 0}
      onRefresh={fetch}
    >
      <Segmented options={(['1M', '3M', 'All'] as const).map((k) => ({ key: k, label: k }))} value={range} onChange={setRange} />
      {loading && rows.length === 0 ? (
        <Loading label="Loading activity" />
      ) : error && rows.length === 0 ? (
        <PanelError title="Couldn't load activity" detail={error} onRetry={fetch} />
      ) : statement.length === 0 ? (
        <EmptyState title="Nothing in this range" detail="Fills, transfers and dividends appear here as they happen." />
      ) : (
        <>
          {lanes.length ? (
            <Card style={s.lanes}>
              <Lanes lanes={lanes} from={from} until={now} now={now} labelWidth={28} />
              <View style={s.ticks}>
                <Text variant="numSmall" tone="fg3" style={s.tick}>
                  {dayLabel(from, now)}
                </Text>
                <Text variant="numSmall" tone="fg3" style={s.tick}>
                  Today
                </Text>
              </View>
            </Card>
          ) : null}
          {days.map((d) => (
            <View key={d.day} style={s.day}>
              <Text variant="subhead">{dayLabel(d.day, now)}</Text>
              <Card style={s.list}>
                {d.rows.map((r, i) => (
                  <View key={r.id} style={[s.row, i < d.rows.length - 1 ? s.divider : null]}>
                    <View style={[s.tag, r.kind === 'deposit' ? s.tagIn : null]}>
                      <Text variant="numSmall" tone="fg2" style={[s.tagText, r.kind === 'deposit' ? s.tagTextIn : null]}>
                        {statementTag(r.kind)}
                      </Text>
                    </View>
                    <View style={s.flex}>
                      <Text variant="small" numberOfLines={1}>
                        {r.label}
                      </Text>
                      <Text variant="caption" tone="fg3" numberOfLines={1}>
                        {[r.sleeveId ? nameOf(r.sleeveId) : r.sublabel, r.account, hm(r.t)].filter(Boolean).join(' · ')}
                      </Text>
                    </View>
                    <PaperAmount paper={r.account === 'paper'} variant="numSmall" tone={r.signed === 0 ? 'fg2' : 'fg'}>
                      {r.signed === 0 ? money(r.amount, 2) : signedMoney(r.signed, 2)}
                    </PaperAmount>
                  </View>
                ))}
              </Card>
            </View>
          ))}
          <Text variant="caption" tone="fg3" style={s.center}>
            Amounts show the effect on free cash. Trades inside a session show their value.
          </Text>
          {hasMore && range === 'All' ? (
            <Button label="Load more" variant="secondary" loading={loadingMore} onPress={loadMore} />
          ) : null}
        </>
      )}
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1, minWidth: 0 },
  center: { textAlign: 'center' },
  lanes: { paddingVertical: 12, gap: 6 },
  ticks: { flexDirection: 'row', justifyContent: 'space-between', paddingLeft: 28 },
  tick: { fontSize: 10.5 },
  day: { gap: 8 },
  list: { paddingVertical: 2 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  tag: { minWidth: 40, alignItems: 'center', borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.xs, paddingVertical: 1, paddingHorizontal: 3 },
  tagIn: { backgroundColor: t.c.fg, borderColor: t.c.fg },
  tagText: { fontSize: 10.5, lineHeight: 14 },
  tagTextIn: { color: t.c.canvas },
}));
