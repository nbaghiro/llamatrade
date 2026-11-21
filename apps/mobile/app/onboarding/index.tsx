import { useBacktestStore } from '@llamatrade/core/stores/backtest';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { router, type Href } from 'expo-router';
import { Blocks, ChevronRight, LayoutTemplate, type LucideIcon } from 'lucide-react-native';
import { useEffect } from 'react';
import { View } from 'react-native';

import { StepLine } from '../../src/account/parts';
import { useAuthStore } from '../../src/stores/auth';
import { makeStyles, useTheme } from '../../src/theme';
import { Card, CopilotMark, Screen, Text } from '../../src/ui';

interface Way {
  key: string;
  title: string;
  body: string;
  icon: LucideIcon | 'copilot';
  href: Href;
}

const WAYS: readonly Way[] = [
  {
    key: 'template',
    title: 'Start from a template',
    body: 'Ready-made strategies with their rules written out. Run one as it is or change it first.',
    icon: LayoutTemplate,
    href: '/templates',
  },
  {
    key: 'copilot',
    title: 'Describe it to Copilot',
    body: 'Say what you want in a sentence. Copilot drafts the rules, and you check them before anything runs.',
    icon: 'copilot',
    href: '/(tabs)/copilot',
  },
  {
    key: 'blocks',
    title: 'Build from blocks',
    body: 'Put conditions, holdings and a schedule together yourself, one block at a time.',
    icon: Blocks,
    href: '/builder/new',
  },
];

function WayCard({ way }: { way: Way }) {
  const { c } = useTheme();
  const s = useStyles();
  const Icon = way.icon;
  return (
    <Card style={s.way} onPress={() => router.push(way.href)}>
      <View style={s.wayHead}>
        {Icon === 'copilot' ? <CopilotMark size={20} /> : <Icon color={c.accent} size={20} strokeWidth={1.7} />}
        <Text variant="subhead" style={s.flex}>{way.title}</Text>
        <ChevronRight color={c.fg3} size={16} strokeWidth={1.8} />
      </View>
      <Text variant="small" tone="fg2">{way.body}</Text>
      <Text variant="caption" tone="fg3">Ends in a backtest · no broker needed</Text>
    </Card>
  );
}

export default function OnboardingScreen() {
  const s = useStyles();
  const user = useAuthStore((st) => st.user);
  const credentials = useBrokerStore((st) => st.credentials);
  const fetchBroker = useBrokerStore((st) => st.fetch);
  const recentRuns = useBacktestStore((st) => st.recentRuns);
  const fetchRecentRuns = useBacktestStore((st) => st.fetchRecentRuns);

  useEffect(() => {
    fetchBroker().catch(() => undefined);
    fetchRecentRuns(1).catch(() => undefined);
  }, [fetchBroker, fetchRecentRuns]);

  const paper = credentials.some((cr) => cr.isPaper);
  const first = user?.firstName?.trim();
  const latest = recentRuns[0];

  return (
    <Screen
      title={first ? `Welcome, ${first}` : 'Welcome'}
      tab
      art="bold"
      artSeed="onboarding-start"
    >
      <Text variant="body" tone="fg2" style={s.lede}>
        Make a first strategy and see how it would have done. Pick whichever way suits you.
      </Text>

      {latest ? (
        <Card style={s.latest} onPress={() => router.push({ pathname: '/onboarding/result/[id]', params: { id: latest.id } })}>
          <Text variant="label" tone="fg3">Your latest backtest</Text>
          <Text variant="bodyStrong">Open the result, with what it held and when</Text>
        </Card>
      ) : null}

      {WAYS.map((w) => (
        <WayCard key={w.key} way={w} />
      ))}

      <Card style={s.path}>
        <StepLine current={0} />
        <Text variant="caption" tone="fg3">
          {paper
            ? 'Alpaca paper is connected, so a backtest you like can start on paper next.'
            : 'Paper sessions need Alpaca paper, which isn’t connected yet. Live is a separate connection, when you choose.'}
        </Text>
        {!paper ? (
          <Text variant="small" tone="accent" onPress={() => router.push({ pathname: '/account/connect-broker', params: { env: 'paper' } })}>
            Connect Alpaca paper
          </Text>
        ) : null}
      </Card>
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  flex: { flex: 1 },
  lede: { marginTop: -6 },
  way: { gap: 8 },
  wayHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  latest: { gap: 4 },
  path: { gap: 10 },
}));
