import { money } from '@llamatrade/core/format';
import { router } from 'expo-router';
import { useMemo } from 'react';
import { View } from 'react-native';

import { useHomeData } from '../../src/home/data';
import { displayName, type Mode } from '../../src/home/model';
import { PaperAmount } from '../../src/home/PaperAmount';
import { makeStyles, radius } from '../../src/theme';
import { Card, Loading, Notice, Screen, Text } from '../../src/ui';

/**
 * Checks against Alpaca (reconciliation2 A). The ledger side of the bridge is shown per account;
 * the Alpaca side needs a reconciliation read the API doesn't offer yet, so it says so.
 */
export default function ChecksScreen() {
  const s = useStyles();
  const d = useHomeData();
  const accounts = useMemo(() => {
    const out: { mode: Mode; sessions: number; cash: number | null; frozen: string[] }[] = [];
    for (const mode of ['live', 'paper'] as const) {
      const mine = d.sessions.filter((x) => x.mode === mode && x.state !== 'stopped');
      const cash = mode === 'live' ? d.liveCash : d.paperCash;
      if (mine.length === 0 && cash === null) continue;
      out.push({
        mode,
        sessions: mine.reduce((sum, x) => sum + (x.value ?? 0), 0),
        cash,
        frozen: mine.filter((x) => x.state === 'frozen').map((x) => displayName(x.name)),
      });
    }
    return out;
  }, [d.sessions, d.liveCash, d.paperCash]);

  return (
    <Screen
      title="Checks"
      artSeed="portfolio-checks-bridge"
      art="bold"
      back={{ label: 'Portfolio', onPress: () => (router.canGoBack() ? router.back() : router.replace('/portfolio')) }}
      refreshing={d.refreshing}
      onRefresh={d.refresh}
    >
      {d.loading ? (
        <Loading label="Loading the ledger" />
      ) : (
        <>
          <Text variant="body" tone="fg2">
            Each account's ledger, as LlamaTrade records it. A frozen session means its holdings in Alpaca and the ledger disagree.
          </Text>
          {accounts.map((a) => (
            <Card key={a.mode} style={[s.card, a.frozen.length ? s.cardRisk : null, a.mode === 'paper' ? s.cardPaper : null]}>
              <View style={s.head}>
                <View style={[s.modeTag, a.mode === 'live' ? s.modeTagLive : null]}>
                  <Text variant="numSmall" style={[s.modeTagText, a.mode === 'live' ? s.modeTagTextLive : null]}>
                    {a.mode === 'live' ? 'LIVE' : 'PAPER'}
                  </Text>
                </View>
                {a.frozen.length ? (
                  <Text variant="small" tone="risk">
                    {a.frozen.length === 1 ? `${a.frozen[0]} is frozen` : `${a.frozen.length} sessions frozen`}
                  </Text>
                ) : (
                  <Text variant="small" tone="fg3">
                    No frozen sessions
                  </Text>
                )}
              </View>
              <BridgeRow label="Sessions, ledger" value={a.sessions} paper={a.mode === 'paper'} />
              <BridgeRow label="Cash, unallocated" value={a.cash} paper={a.mode === 'paper'} />
              <BridgeRow label="Ledger total" value={a.sessions + (a.cash ?? 0)} paper={a.mode === 'paper'} strong last />
            </Card>
          ))}
          <Notice
            tone="neutral"
            title="The Alpaca side isn't in the app yet."
            detail="Comparing each figure with Alpaca's own equity needs a reconciliation read the API doesn't offer yet. Frozen sessions still show here and on Sessions."
          />
          {accounts.some((a) => a.frozen.length) ? (
            <Text variant="small" tone="accent" onPress={() => router.push('/sessions')}>
              Open Sessions to resolve
            </Text>
          ) : null}
        </>
      )}
    </Screen>
  );
}

function BridgeRow({ label, value, paper, strong = false, last = false }: { label: string; value: number | null; paper: boolean; strong?: boolean; last?: boolean }) {
  const s = useStyles();
  return (
    <View style={[s.row, last ? null : s.divider]}>
      <Text variant={strong ? 'bodyStrong' : 'small'} tone={strong ? 'fg' : 'fg2'} style={s.flex}>
        {label}
      </Text>
      {value === null ? (
        <Text variant="numSmall" tone="fg3">
          Couldn't be read
        </Text>
      ) : (
        <PaperAmount paper={paper} variant={strong ? 'numStrong' : 'num'}>
          {money(value, 2)}
        </PaperAmount>
      )}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  card: { paddingVertical: 4 },
  cardPaper: { borderStyle: 'dashed', borderColor: t.c.lineStrong },
  cardRisk: { borderColor: t.c.riskLine, borderStyle: 'solid' },
  head: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10 },
  modeTag: { borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.pill, paddingHorizontal: 7, paddingVertical: 1 },
  modeTagLive: { backgroundColor: t.c.fg, borderColor: t.c.fg },
  modeTagText: { fontSize: 10, lineHeight: 14, color: t.c.fg2, letterSpacing: 0.4 },
  modeTagTextLive: { color: t.c.canvas },
  row: { flexDirection: 'row', alignItems: 'center', paddingVertical: 10 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
}));
