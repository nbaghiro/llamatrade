import { num, pct, toDate } from '@llamatrade/core/format';
import { BacktestStatus, type BacktestRun } from '@llamatrade/core/proto/backtest_pb';
import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { router, useLocalSearchParams } from 'expo-router';
import { AlertCircle } from 'lucide-react-native';
import { useEffect, useMemo, useState } from 'react';
import { View } from 'react-native';

import { AxisLabels, Curve, Lanes } from '../../src/backtests/charts';
import { heldSpans, pointsOf } from '../../src/backtests/data';
import { cagr, lanesOf, progressFraction, resultSentence, runTitle, worstStretch, type Point } from '../../src/backtests/model';
import { useSessionRows } from '../../src/sessions/data';
import { shortDate } from '../../src/strategies/model';
import { makeStyles, useTheme } from '../../src/theme';
import { Button, Card, Loading, Meter, Notice, PanelError, Screen, Segmented, Text, pnlTone } from '../../src/ui';

const LOG_AFTER_YEARS = 8;

function yearLabels(points: readonly Point[]): string[] {
  if (points.length < 2) return [];
  const a = new Date(points[0].at).getUTCFullYear();
  const b = new Date(points[points.length - 1].at).getUTCFullYear();
  const mid = new Date(points[Math.floor(points.length / 2)].at).getUTCFullYear();
  return a === b ? [shortDate(points[0].at), shortDate(points[points.length - 1].at)] : [String(a), String(mid), String(b)];
}

function Figure({ label, value, tone, sub }: { label: string; value: string; tone?: 'fg' | 'gain' | 'loss'; sub?: string }) {
  const s = useStyles();
  return (
    <View style={s.figure}>
      <Text variant="label" tone="fg3" style={s.caps}>{label}</Text>
      <Text variant="numLarge" tone={tone ?? 'fg'}>{value}</Text>
      {sub ? <Text variant="numSmall" tone="fg3">{sub}</Text> : null}
    </View>
  );
}

function Results({ run, name }: { run: BacktestRun; name: string }) {
  const s = useStyles();
  const { c } = useTheme();
  const rows = useSessionRows();
  const [scale, setScale] = useState<'linear' | 'log'>('linear');
  const m = run.results?.metrics;
  const points = pointsOf(run.results?.equityCurve);
  const bench = pointsOf(run.results?.benchmarkEquityCurve);
  const benchSym = run.results?.benchmarkSymbol || run.config?.benchmarkSymbol || 'SPY';
  const start = points[0]?.at ?? 0;
  const end = points[points.length - 1]?.at ?? 0;
  const ret = m ? num(m.totalReturn) : null;
  const benchRet = m?.benchmarkReturn?.value ? num(m.benchmarkReturn) : null;
  const dd = m ? -Math.abs(num(m.maxDrawdown)) : null;
  const worst = useMemo(() => worstStretch(points), [points]);
  const benchWorst = useMemo(() => worstStretch(bench), [bench]);
  const spans = useMemo(() => heldSpans(run.results?.trades ?? [], end), [run, end]);
  const lanes = useMemo(() => lanesOf(spans, start, end, 4), [spans, start, end]);
  const years = (end - start) / (365.25 * 86_400_000);
  const long = years >= LOG_AFTER_YEARS;
  const growth = ret !== null ? cagr(ret, start, end) : null;
  const benchGrowth = benchRet !== null ? cagr(benchRet, start, end) : null;
  const sentence = ret !== null ? resultSentence(ret, benchRet, dd, benchWorst?.depth ?? null, benchSym) : null;
  const heldInWorst = worst
    ? [...new Set(spans.filter((sp) => sp.from <= worst.to && sp.to >= worst.from).map((sp) => sp.symbol))].slice(0, 3)
    : [];
  const band = worst && end > start ? [{ from: (worst.from - start) / (end - start), to: (worst.to - start) / (end - start), tone: 'loss' as const }] : [];
  const session = rows.find((r) => r.strategyId === run.strategyId && r.state !== 'stopped');

  return (
    <>
      <View style={s.headLine}>
        <Text variant="label" tone="fg3" style={s.caps}>TOTAL RETURN</Text>
        <Text variant="label" tone="fg3">Backtest</Text>
      </View>
      <Text variant="hero" tone={ret === null ? 'fg3' : pnlTone(ret)} style={s.hero}>{ret === null ? '–' : pct(ret * 100, 1)}</Text>
      {sentence ? <Text variant="small" tone="fg2">{sentence}</Text> : null}

      {long ? (
        <Segmented options={[{ key: 'linear', label: 'Linear' }, { key: 'log', label: 'Log scale' }]} value={scale} onChange={setScale} />
      ) : null}
      <View>
        <Curve values={points.map((p) => p.value)} benchmark={bench.length > 1 ? bench.map((p) => p.value) : undefined} height={170} bands={band} log={scale === 'log'} />
        <Lanes lanes={lanes} />
        <AxisLabels labels={yearLabels(points)} />
      </View>

      {m ? (
        <Card style={s.figures}>
          <Figure label="CAGR" value={growth === null ? '–' : `${(growth * 100).toFixed(1)}%`} sub={benchGrowth === null ? undefined : `${benchSym} ${(benchGrowth * 100).toFixed(1)}%`} />
          <View style={s.divider} />
          <Figure label="SHARPE" value={num(m.sharpeRatio).toFixed(2)} />
          <View style={s.divider} />
          <Figure label="DRAWDOWN" value={dd === null ? '–' : pct(dd * 100, 1)} tone="loss" sub={benchWorst ? `${benchSym} ${pct(benchWorst.depth * 100, 1)}` : undefined} />
        </Card>
      ) : null}

      {worst ? (
        <Card style={s.worst}>
          <AlertCircle color={c.fg3} size={18} strokeWidth={1.6} />
          <View style={s.flex}>
            <Text variant="bodyStrong">Worst stretch</Text>
            <Text variant="small" tone="fg3">
              {shortDate(worst.from, 0)} to {shortDate(worst.to, 0)}
              {heldInWorst.length ? ` · held ${heldInWorst.join(', ')}` : ''}
            </Text>
            <Text variant="caption" tone="fg3">{worst.recovered ? `Back to its peak by ${shortDate(worst.recovered, 0)}` : 'Not back to its peak by the end of the run'}</Text>
          </View>
          <Text variant="numStrong" tone="loss">{pct(worst.depth * 100, 1)}</Text>
        </Card>
      ) : null}

      <Text variant="caption" tone="fg3">
        {run.config?.startDate ? `${shortDate(toDate(run.config.startDate)?.getTime() ?? 0, 0)} to ${shortDate(toDate(run.config.endDate)?.getTime() ?? 0, 0)}` : ''}
        {m ? ` · ${m.totalTrades} trades` : ''}. Simulated on daily bars; past results don't promise future ones.
      </Text>

      {session ? (
        <Button label={`Open the ${session.mode} session`} onPress={() => router.push(`/sessions/${session.id}`)} />
      ) : (
        <Button label="Start on paper" onPress={() => router.push(`/sessions/start?strategy=${run.strategyId}`)} />
      )}
      <Button label="Run again with new settings" variant="secondary" onPress={() => router.push(`/backtests/new?strategy=${run.strategyId}&version=${run.strategyVersion}`)} />
    </>
  );
}

function Running({ run }: { run: BacktestRun }) {
  const s = useStyles();
  const { progress, progressEvents, partialMetrics, cancelBacktest } = useBacktestStore();
  const [cancelling, setCancelling] = useState(false);
  const last = progressEvents[progressEvents.length - 1];
  const percent = Math.max(progress, run.progressPercent);
  const through = last?.currentDate || run.currentDate;
  const partial = partialMetrics?.totalReturn?.value ? num(partialMetrics.totalReturn) * 100 : null;
  const worst = partialMetrics?.maxDrawdown?.value ? -Math.abs(num(partialMetrics.maxDrawdown)) * 100 : null;
  return (
    <>
      <View style={s.headLine}>
        <View style={s.status}>
          <View style={[s.dot, s.dotRun]} />
          <Text variant="small" tone="fg2">Simulating · {Math.round(percent)}%</Text>
        </View>
        <Text variant="label" tone="fg3">Backtest</Text>
      </View>
      {partial !== null ? (
        <>
          <Text variant="hero" tone={pnlTone(partial)} style={s.hero}>{pct(partial, 1)}</Text>
          <Text variant="small" tone="fg3">so far{through ? `, through ${through.slice(0, 10)}` : ''}</Text>
        </>
      ) : (
        <Text variant="small" tone="fg3">{through ? `Simulated through ${through.slice(0, 10)}` : 'Loading prices and warming up indicators'}</Text>
      )}
      <Meter value={progressFraction(percent)} height={6} />
      <Card style={s.steps}>
        {(progressEvents.length ? progressEvents.slice(-4) : [{ message: 'Waiting for the first update', atMs: 0, percent: 0, currentDate: '', status: run.status }]).map((e, i) => (
          <Text key={`${e.atMs}-${i}`} variant="small" tone={i === Math.min(progressEvents.length, 4) - 1 ? 'fg' : 'fg3'}>{e.message || `${e.percent}%`}</Text>
        ))}
      </Card>
      {worst !== null ? (
        <Card style={s.figures}>
          <Figure label="WORST FALL" value={pct(worst, 1)} tone="loss" sub="so far" />
        </Card>
      ) : null}
      <Text variant="caption" tone="fg3">The curve appears when the run finishes; the service doesn't send it while the run is going. You can leave this screen and the run carries on.</Text>
      <Button
        label="Cancel run"
        variant="secondary"
        loading={cancelling}
        onPress={async () => {
          setCancelling(true);
          await cancelBacktest(run.id);
          setCancelling(false);
        }}
      />
    </>
  );
}

function Stopped({ run }: { run: BacktestRun }) {
  const s = useStyles();
  const cancelled = run.status === BacktestStatus.CANCELLED;
  return (
    <>
      <View style={s.headLine}>
        <View style={s.status}>
          <View style={[s.dot, s.dotRisk]} />
          <Text variant="small" tone="risk">{cancelled ? 'Cancelled' : 'Couldn’t finish'}</Text>
        </View>
        <Text variant="label" tone="fg3">Backtest</Text>
      </View>
      <Notice
        title={cancelled ? 'You cancelled this run.' : run.currentDate ? `Stopped at ${run.currentDate.slice(0, 10)}.` : 'The run stopped.'}
        detail={run.statusMessage || (cancelled ? undefined : 'The service gave no reason.')}
      />
      <Text variant="caption" tone="fg3">The service doesn't keep a stopped run's curve, so there's no partial result to show.</Text>
      <Button label="Run again" onPress={() => router.push(`/backtests/new?strategy=${run.strategyId}&version=${run.strategyVersion}`)} />
    </>
  );
}

export default function BacktestRunScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { currentBacktest, loading, error, getBacktest, streamProgress, streaming } = useBacktestStore();
  const { strategies, fetchStrategies } = useStrategiesStore();

  useEffect(() => {
    if (!id) return;
    const st = useBacktestStore.getState();
    if (st.currentBacktest?.id !== id || !st.streaming) {
      getBacktest(id).then(() => {
        const run = useBacktestStore.getState().currentBacktest;
        if (run && (run.status === BacktestStatus.RUNNING || run.status === BacktestStatus.PENDING) && !useBacktestStore.getState().streaming) {
          streamProgress(id).catch(() => undefined);
        }
      });
    }
    if (!useStrategiesStore.getState().strategies.length) fetchStrategies();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [id]);

  const run = currentBacktest?.id === id ? currentBacktest : null;
  const name = strategies.find((x) => x.id === run?.strategyId)?.name ?? 'Backtest';
  const title = run ? runTitle(name, run.strategyVersion) : 'Backtest';
  const back = { label: 'Backtests', onPress: () => (router.canGoBack() ? router.back() : router.replace('/backtests')) };
  const done = run?.status === BacktestStatus.COMPLETED;
  const going = run?.status === BacktestStatus.RUNNING || run?.status === BacktestStatus.PENDING;

  return (
    <Screen title={title} back={back} art="bold" artSeed={`backtest-${id ?? ''}`} refreshing={false} onRefresh={id && !streaming ? () => getBacktest(id) : undefined}>
      {!run ? (
        loading ? <Loading label="Loading the run" /> : <PanelError title="This run could not be loaded" detail={error ?? undefined} onRetry={id ? () => getBacktest(id) : undefined} />
      ) : done ? (
        <Results run={run} name={name} />
      ) : going ? (
        <Running run={run} />
      ) : (
        <Stopped run={run} />
      )}
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  headLine: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: -6 },
  caps: { letterSpacing: 0.6, fontSize: 11 },
  hero: { marginTop: -8 },
  figures: { flexDirection: 'row', paddingHorizontal: 12 },
  figure: { flex: 1, gap: 3 },
  divider: { width: 1, backgroundColor: t.c.line, marginHorizontal: 10 },
  worst: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  flex: { flex: 1, gap: 2 },
  center: { textAlign: 'center' },
  status: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dot: { width: 7, height: 7, borderRadius: 4 },
  dotRun: { backgroundColor: t.c.accent },
  dotRisk: { backgroundColor: t.c.risk },
  steps: { gap: 6 },
}));
