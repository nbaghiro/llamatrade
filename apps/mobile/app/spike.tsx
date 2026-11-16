import { router } from 'expo-router';
import { useRef, useState } from 'react';
import { View } from 'react-native';

import {
  runBacktestProgressSpike,
  runCopilotStreamSpike,
  type SpikeResult,
} from '../src/spike/streamingSpike';
import { useAuthStore } from '../src/stores/auth';
import { Button, Card, Field, Pill, Screen, Text } from '../src/ui';

export default function SpikeScreen() {
  const user = useAuthStore((s) => s.user);
  const [backtestId, setBacktestId] = useState('');
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<SpikeResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const run = async (which: 'copilot' | 'backtest') => {
    setResult(null);
    setRunning(true);
    const ac = new AbortController();
    abortRef.current = ac;
    const res =
      which === 'copilot'
        ? await runCopilotStreamSpike({ signal: ac.signal })
        : await runBacktestProgressSpike(backtestId, ac.signal);
    setResult(res);
    setRunning(false);
  };

  return (
    <Screen title="Streaming spike" back={{ label: 'Close', onPress: () => router.back() }}>
      <Text variant="small" tone="fg2">
        Checks that Connect server streaming works over expo/fetch in React Native: events should arrive one
        at a time, not as one buffered response.
      </Text>

      <Card style={{ gap: 4 }}>
        <Text variant="label" tone="fg3">Session</Text>
        {user ? (
          <>
            <Text variant="num">{user.email}</Text>
            <Text variant="numSmall" tone="fg3">tenant {user.tenantId.slice(0, 8)}</Text>
          </>
        ) : (
          <Text variant="small" tone="risk">Not signed in. Sign in first.</Text>
        )}
      </Card>

      <View style={{ flexDirection: 'row', gap: 8 }}>
        <Button label={running ? 'Running' : 'Copilot stream'} onPress={() => run('copilot')} loading={running} style={{ flex: 1 }} />
        {running ? (
          <Button label="Cancel" variant="danger" onPress={() => abortRef.current?.abort()} style={{ flex: 1 }} />
        ) : null}
      </View>

      <Card style={{ gap: 10 }}>
        <Field label="Backtest ID for the progress spike" value={backtestId} onChange={setBacktestId} placeholder="backtest uuid" mono />
        <Button label="Backtest progress" variant="secondary" onPress={() => run('backtest')} />
      </Card>

      {result ? (
        <Card style={{ gap: 6 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
            <Pill label={result.pass ? 'Pass' : 'Fail'} tone={result.pass ? 'accent' : 'risk'} />
            <Text variant="numSmall" tone="fg2">
              {result.deltaCount} events · first at {result.firstEventMs ?? '–'}ms
            </Text>
          </View>
          {result.error ? <Text variant="numSmall" tone="risk">{result.error}</Text> : null}
          {result.logs.map((l, i) => (
            <Text key={i} variant="numSmall" tone="fg3">
              {String(l.atMs).padStart(5, ' ')}ms {l.line}
            </Text>
          ))}
        </Card>
      ) : null}
    </Screen>
  );
}
