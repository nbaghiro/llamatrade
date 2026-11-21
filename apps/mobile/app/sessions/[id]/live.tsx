import { money, num, toDate } from '@llamatrade/core/format';
import { useDeployStore } from '@llamatrade/core/stores/deploy';
import { readLiveAccount, type LiveAccount } from '@llamatrade/core/stores/funding';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { router, useLocalSearchParams } from 'expo-router';
import { Check, Lock } from 'lucide-react-native';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';

import { LineChart } from '../../../src/charts/LineChart';
import { amountProblem, parseAmount, suggestAmount } from '../../../src/sessions/amount';
import { AmountField } from '../../../src/sessions/AmountField';
import { day, fillsOf } from '../../../src/sessions/data';
import { displayName, laneX, rebalanceDays } from '../../../src/sessions/model';
import { LabelledLane } from '../../../src/sessions/parts';
import { InkButton } from '../../../src/sessions/Sheet';
import { makeStyles, radius, useTheme } from '../../../src/theme';
import { Card, Loading, Notice, PanelError, Screen, Text, pnlTone } from '../../../src/ui';

type LiveRead = { state: 'loading' } | { state: 'none' } | { state: 'error'; message: string } | { state: 'ready'; account: LiveAccount };

/** From paper to live (sessions/golive2 A): the paper record, the amount, one statement, one checkbox. */
export default function GoLiveScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const detail = useTradingStore((st) => (st.detail?.session.id === id ? st.detail : null));
  const { deploy, deploying, error: deployError, clearError } = useDeployStore();
  const [live, setLive] = useState<LiveRead>({ state: 'loading' });
  const [text, setText] = useState('');
  const [agreed, setAgreed] = useState(false);
  const [liveError, setLiveError] = useState<string | null>(null);

  useEffect(() => {
    if (id && !detail) useTradingStore.getState().loadSession(id, new Date(Date.now() - 400 * 86_400_000)).catch(() => undefined);
  }, [id, detail]);

  useEffect(() => {
    clearError();
    let on = true;
    readLiveAccount()
      .then((account) => {
        if (!on) return;
        setLive(account ? { state: 'ready', account } : { state: 'none' });
        if (account && account.unallocatedCash > 0) setText(String(suggestAmount(account.unallocatedCash)));
      })
      .catch((e: unknown) => on && setLive({ state: 'error', message: e instanceof Error ? e.message : 'The live account could not be read.' }));
    return () => {
      on = false;
    };
  }, [clearError]);

  const title = detail ? displayName(detail.session.name) : 'Session';
  const back = { label: title, onPress: () => (router.canGoBack() ? router.back() : router.replace({ pathname: '/sessions/[id]', params: { id: id ?? '' } })) };
  const values = detail ? detail.curve.map((p) => num(p.equity)) : [];
  const started = toDate(detail?.session.startedAt)?.getTime() ?? null;
  const record = values.length > 1 && values[0] > 0 ? (values[values.length - 1] / values[0] - 1) * 100 : null;
  const marks = useMemo(() => {
    if (!detail) return [];
    const start = started ?? Date.now();
    return rebalanceDays(fillsOf(detail.orders.filter((o) => o.sessionId === detail.session.id))).map((d) => ({ x: laneX(d.at, start, Date.now()), side: 'buy' as const }));
  }, [detail, started]);

  const available = live.state === 'ready' ? live.account.unallocatedCash : null;
  const amount = parseAmount(text);
  const problem = amountProblem(amount, available);
  const label = amount !== null ? money(amount, 0) : '$0';

  const start = async () => {
    if (!detail || live.state !== 'ready' || problem || amount === null || !agreed) return;
    const res = await deploy({
      strategyId: detail.session.strategyId,
      strategyName: title,
      strategyVersion: detail.execution?.version ?? 0,
      allocation: amount,
      goLive: true,
      mode: 'live',
      account: { credentialsId: live.account.credentialsId, unallocatedCash: live.account.unallocatedCash },
    });
    if (!res) return;
    useTradingStore.getState().loadBlotter().catch(() => undefined);
    if (res.liveError) setLiveError(res.liveError);
    else if (res.sessionId) router.replace({ pathname: '/sessions/[id]', params: { id: res.sessionId } });
    else router.replace('/sessions');
  };

  return (
    <Screen title="Run on live" back={back} art="bold" artSeed={`golive-${id}`}>
      <Text variant="small" tone="fg2" style={s.subtitle}>{title} keeps running on paper. This starts a second session on your live account.</Text>

      <Card style={s.record}>
        <View style={s.recordHead}>
          <Text variant="label" tone="fg3">{started ? `PAPER SINCE ${day(started).toUpperCase()}` : 'PAPER RECORD'}</Text>
          {record !== null ? <Text variant="num" tone={pnlTone(record)}>{`${record >= 0 ? '+' : '−'}${Math.abs(record).toFixed(1)}%`}</Text> : null}
        </View>
        {values.length > 1 ? <LineChart values={values} height={120} /> : <Loading label="Loading the paper record" />}
        <LabelledLane label="Paper" marks={marks} to={1} />
        <View style={[s.liveLane, { borderColor: c.line }]}>
          <Text variant="numSmall" style={s.laneLabel}>Live</Text>
          <Text variant="small" tone="fg3" style={s.flex}>starts when you confirm</Text>
          <View style={[s.nowTick, { backgroundColor: c.fg }]} />
        </View>
      </Card>

      {live.state === 'loading' ? <Loading label="Checking your live account" /> : null}
      {live.state === 'error' ? <PanelError title="The live account could not be read" detail={live.message} /> : null}
      {live.state === 'none' ? (
        <Notice
          title="No live Alpaca account is connected."
          detail="Connect one from Account, then come back here."
          action={<Text variant="smallStrong" tone="accent" onPress={() => router.push('/account/connect-broker')}>Connect Alpaca</Text>}
        />
      ) : null}

      {live.state === 'ready' ? (
        <>
          {available !== null && available <= 0 ? (
            <Notice title="The live account has no free cash yet." detail="A live session starts from the live account's unallocated cash, and there is none to draw from." />
          ) : null}
          <AmountField label="Amount for the live session" value={text} onChange={setText} available={available} error={text ? problem : null} />
          <View style={[s.statement, { backgroundColor: c.sunk, borderColor: c.line, borderLeftColor: c.fg }]}>
            <Lock color={c.fg} size={16} strokeWidth={1.8} style={s.lock} />
            <Text variant="small" style={s.flex}>
              <Text variant="smallStrong">This uses real money. </Text>
              Orders go to your Alpaca live account automatically at every rebalance, with no paper step in between.
            </Text>
          </View>
          <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: agreed }} onPress={() => setAgreed((v) => !v)} style={s.agree}>
            <View style={[s.box, agreed ? { backgroundColor: c.accentFill, borderColor: c.accentFill } : { borderColor: c.lineStrong }]}>
              {agreed ? <Check color={c.accentInk} size={13} strokeWidth={2.4} /> : null}
            </View>
            <Text variant="small">I understand these are real orders.</Text>
          </Pressable>
          {deployError ? <Notice title="It didn't start." detail={deployError} /> : null}
          {liveError ? <Notice title="The live sleeve is funded, but the session didn't start." detail={liveError} /> : null}
          <InkButton label={`Start live with ${label}`} onPress={start} loading={deploying} disabled={!agreed || problem !== null || !detail} />
        </>
      ) : null}
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  flex: { flex: 1 },
  subtitle: { marginTop: -8 },
  record: { gap: 8, borderRadius: radius.lg },
  recordHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  liveLane: { flexDirection: 'row', alignItems: 'center', gap: 8, borderTopWidth: 1, paddingVertical: 6 },
  laneLabel: { width: 44, fontSize: 11 },
  nowTick: { width: 2.5, height: 14, borderRadius: 1 },
  statement: { flexDirection: 'row', gap: 10, borderWidth: 1, borderLeftWidth: 3, borderRadius: radius.md, padding: 12 },
  lock: { marginTop: 2 },
  agree: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  box: { width: 20, height: 20, borderRadius: 5, borderWidth: 1.5, alignItems: 'center', justifyContent: 'center' },
}));
