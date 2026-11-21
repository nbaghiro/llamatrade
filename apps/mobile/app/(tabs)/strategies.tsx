import { money, pct, signedMoney } from '@llamatrade/core/format';
import type { Strategy } from '@llamatrade/core/proto/strategy_pb';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { router } from 'expo-router';
import { ChevronRight, FlaskConical, Layers } from 'lucide-react-native';
import { useEffect, useMemo } from 'react';
import { View } from 'react-native';

import { Curve, LineKey } from '../../src/backtests/charts';
import type { SessionRow } from '../../src/sessions/model';
import { sessionFacts, useSameDates, useSessionsWithCurves } from '../../src/strategies/data';
import { gapLabel, listSummary, sortNotRunning, stageLine, stageOf, type DatedValue, type Stage } from '../../src/strategies/model';
import { BlocksIcon, CopilotIcon, ModeTag, NewStrategyActions, StageTrack, WayRow } from '../../src/strategies/parts';
import { makeStyles, useTheme } from '../../src/theme';
import { Button, Card, ListRow, Loading, Notice, Screen, Text, pnlTone } from '../../src/ui';

function RunningCard({ row, points }: { row: SessionRow; points: DatedValue[] }) {
  const s = useStyles();
  const same = useSameDates(row.strategyId, points, row.startedAt, row.version);
  const ready = same.status === 'ready' ? same.same : null;
  const sessionPct = ready ? ready.session[ready.session.length - 1] * 100 : row.returnAllPct;
  const backtestPct = ready ? ready.backtest[ready.backtest.length - 1] * 100 : null;
  return (
    <Card onPress={() => router.push(`/strategy/${row.strategyId}`)} style={[s.running, row.mode === 'live' ? s.runningLive : null]}>
      <View style={s.line}>
        <Text variant="subhead" numberOfLines={1} style={s.flex}>{row.title}</Text>
        <ModeTag mode={row.mode} />
      </View>
      <View style={s.line}>
        <Text variant="numLarge">{row.value === null ? '–' : money(row.value, 2)}</Text>
        {row.today !== null ? <Text variant="numSmall" tone={pnlTone(row.today)}>{signedMoney(row.today, 2)}</Text> : null}
      </View>
      {points.length > 1 ? (
        <Curve
          values={ready ? ready.sessionValues : points.map((p) => p.value)}
          benchmark={ready ? ready.backtestScaled : undefined}
          height={64}
          dot
        />
      ) : (
        <Text variant="caption" tone="fg3">The curve appears after the first day's close.</Text>
      )}
      <View style={s.line}>
        <Text variant="numSmall" tone="fg3" style={s.flex} numberOfLines={1}>
          {sessionPct === null ? null : <Text variant="numSmall" tone={pnlTone(sessionPct)}>{pct(sessionPct, 1)}</Text>}
          {backtestPct !== null ? `  vs ${pct(backtestPct, 1)} backtest` : same.status === 'loading' ? '' : '  No backtest covers these dates'}
        </Text>
        {sessionPct !== null && backtestPct !== null ? <Text variant="numSmall">{gapLabel(sessionPct, backtestPct)}</Text> : null}
      </View>
    </Card>
  );
}

function NotRunningRow({ strategy, stage, backtest, last }: { strategy: Strategy; stage: Stage; backtest: number | undefined; last: boolean }) {
  return (
    <ListRow
      label={strategy.name}
      sub={stageLine(stage, new Date().getUTCFullYear())}
      right={
        backtest === undefined ? (
          <Text variant="numSmall" tone="fg3">No runs</Text>
        ) : (
          <Text variant="numSmall" tone={pnlTone(backtest)}>{pct(backtest, 1)}</Text>
        )
      }
      onPress={() => router.push(`/strategy/${strategy.id}`)}
      last={last}
    />
  );
}

function ThreeWays() {
  const s = useStyles();
  return (
    <>
      <Card style={s.hero}>
        <Text variant="subhead">Start from a template</Text>
        <Text variant="small" tone="fg2">Each template is a complete strategy you can backtest, then change.</Text>
        <Button label="Browse templates" onPress={() => router.push('/templates')} />
      </Card>
      <Card style={s.group}>
        <WayRow icon={<CopilotIcon />} title="Describe it to Copilot" sub="Write the idea in a sentence" onPress={() => router.push('/builder/new')} />
        <WayRow icon={<BlocksIcon />} title="Build from blocks" sub="Set the rules yourself" onPress={() => router.push('/builder/new')} last />
      </Card>
      <StageTrack note="Your first strategy appears here as a draft, then moves right as you test it." />
    </>
  );
}

export default function StrategiesScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { strategies, backtestReturns, loading, error, fetchStrategies, fetchBacktestReturns, clearError } = useStrategiesStore();
  const { rows, curves } = useSessionsWithCurves();

  useEffect(() => {
    fetchStrategies();
    fetchBacktestReturns();
  }, [fetchStrategies, fetchBacktestReturns]);

  const refresh = () => {
    fetchStrategies();
    fetchBacktestReturns();
  };

  const { running, notRunning } = useMemo(() => {
    const facts = sessionFacts(rows);
    const open = rows
      .filter((r) => r.state !== 'stopped' && strategies.some((st) => st.id === r.strategyId))
      .sort((a, b) => Number(b.mode === 'live') - Number(a.mode === 'live') || (a.startedAt ?? 0) - (b.startedAt ?? 0));
    const rest = strategies
      .filter((st) => !open.some((r) => r.strategyId === st.id))
      .map((strategy) => ({ strategy, stage: stageOf(strategy.id, facts, backtestReturns[strategy.id] !== undefined) }));
    return { running: open, notRunning: sortNotRunning(rest) };
  }, [rows, strategies, backtestReturns]);

  const empty = !loading && strategies.length === 0 && !error;

  return (
    <Screen title="Strategies" tab right={<NewStrategyActions />} art="bold" artSeed="strategies-tab" refreshing={loading && strategies.length > 0} onRefresh={refresh}>
      {strategies.length ? <Text variant="small" tone="fg3" style={s.summary}>{listSummary(running.length, notRunning.length)}</Text> : null}
      {error ? <Notice title="Strategies could not be loaded." detail={`${error} Tap to dismiss.`} onPress={clearError} /> : null}

      {loading && strategies.length === 0 ? (
        <Loading label="Loading strategies" />
      ) : empty ? (
        <>
          <Text variant="small" tone="fg3" style={s.summary}>Make your first strategy</Text>
          <ThreeWays />
        </>
      ) : (
        <>
          {running.length ? <LineKey main="Session" dashed="Backtest, same dates" /> : null}
          {running.map((row) => (
            <RunningCard key={row.id} row={row} points={row.executionId ? curves[row.executionId] ?? [] : []} />
          ))}
          {notRunning.length ? (
            <View style={s.section}>
              <View style={s.line}>
                <Text variant="subhead">Not running</Text>
                <Text variant="small" tone="fg3">Backtest</Text>
              </View>
              <Card style={s.group}>
                {notRunning.map(({ strategy, stage }, i) => (
                  <NotRunningRow key={strategy.id} strategy={strategy} stage={stage} backtest={backtestReturns[strategy.id]} last={i === notRunning.length - 1} />
                ))}
              </Card>
            </View>
          ) : null}
          <Card style={s.group}>
            <ListRow
              label={<View style={s.linkLabel}><FlaskConical color={c.accent} size={16} strokeWidth={1.8} /><Text variant="body">Backtests</Text></View>}
              right={<ChevronRight color={c.fg3} size={16} strokeWidth={1.8} />}
              onPress={() => router.push('/backtests')}
            />
            <ListRow
              label={<View style={s.linkLabel}><Layers color={c.accent} size={16} strokeWidth={1.8} /><Text variant="body">Templates</Text></View>}
              right={<ChevronRight color={c.fg3} size={16} strokeWidth={1.8} />}
              onPress={() => router.push('/templates')}
              last
            />
          </Card>
        </>
      )}
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  summary: { marginTop: -8 },
  running: { gap: 8 },
  runningLive: { borderColor: t.c.lineStrong, ...t.shadow.md },
  line: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  flex: { flexShrink: 1 },
  section: { gap: 8, marginTop: 6 },
  group: { paddingVertical: 2 },
  hero: { gap: 10 },
  linkLabel: { flexDirection: 'row', alignItems: 'center', gap: 10 },
}));
