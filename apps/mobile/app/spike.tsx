import { router } from 'expo-router';
import { useRef, useState } from 'react';
import { Pressable, ScrollView, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import {
  runBacktestProgressSpike,
  runCopilotStreamSpike,
  type SpikeResult,
} from '../src/spike/streamingSpike';
import { useAuthStore } from '../src/stores/auth';
import { fonts, palette } from '../src/theme';
import { Badge, Body, Display, Label, Mono } from '../src/ui';

function Btn({ label, tone, onPress }: { label: string; tone: 'primary' | 'ink' | 'danger'; onPress: () => void }) {
  const bg = tone === 'primary' ? palette.orange[500] : tone === 'danger' ? palette.red[500] : palette.ink;
  const fg = tone === 'primary' ? palette.ink : palette.bone;
  return (
    <Pressable
      onPress={onPress}
      style={{ flex: 1, backgroundColor: bg, borderWidth: 2, borderColor: palette.ink, paddingVertical: 11, alignItems: 'center' }}
    >
      <Mono size={11} color={fg} style={{ fontWeight: '700' }}>
        {label}
      </Mono>
    </Pressable>
  );
}

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
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: palette.bone }}>
      <View
        style={{
          height: 46,
          borderBottomWidth: 2,
          borderColor: palette.ink,
          backgroundColor: palette.ink,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingHorizontal: 14,
        }}
      >
        <Display size={16} color={palette.orange[500]}>
          Streaming Spike
        </Display>
        <Pressable onPress={() => router.back()}>
          <Mono size={11} color={palette.bone}>
            CLOSE ✕
          </Mono>
        </Pressable>
      </View>

      <ScrollView contentContainerStyle={{ padding: 14, gap: 12 }}>
        <Body size={13} color={palette.gray[600]}>
          Proves Connect server-streaming works over expo/fetch in React Native — deltas should arrive
          incrementally, not as one buffered blob.
        </Body>

        <View style={{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.paper, padding: 12 }}>
          <Label style={{ marginBottom: 6 }}>Session</Label>
          {user ? (
            <View style={{ gap: 3 }}>
              <Mono size={11}>{user.email}</Mono>
              <Mono size={9} color={palette.gray[500]}>
                tenant {user.tenantId.slice(0, 8)}…
              </Mono>
            </View>
          ) : (
            <Mono size={11} color={palette.red[600]}>
              Not signed in — sign in first.
            </Mono>
          )}
        </View>

        <View style={{ flexDirection: 'row', gap: 8 }}>
          <Btn label={running ? 'RUNNING…' : '▶ COPILOT STREAM'} tone="primary" onPress={() => run('copilot')} />
          {running ? <Btn label="CANCEL" tone="danger" onPress={() => abortRef.current?.abort()} /> : null}
        </View>

        <View style={{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.paper, padding: 12, gap: 8 }}>
          <Label>Backtest ID (for progress spike)</Label>
          <TextInput
            value={backtestId}
            onChangeText={setBacktestId}
            placeholder="backtest uuid"
            placeholderTextColor={palette.gray[400]}
            autoCapitalize="none"
            autoCorrect={false}
            style={{
              borderWidth: 2,
              borderColor: palette.ink,
              backgroundColor: palette.paper,
              fontFamily: fonts.mono,
              fontSize: 12,
              color: palette.ink,
              paddingHorizontal: 9,
              paddingVertical: 8,
            }}
          />
          <Btn label="▶ BACKTEST PROGRESS" tone="ink" onPress={() => run('backtest')} />
        </View>

        {result ? (
          <View style={{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.ink, padding: 12 }}>
            <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 }}>
              <Badge label={result.pass ? 'PASS' : 'FAIL'} variant={result.pass ? 'green' : 'red'} />
              <Mono size={10} color={palette.bone}>
                {result.deltaCount} events · first @ {result.firstEventMs ?? '—'}ms
              </Mono>
            </View>
            {result.error ? (
              <Mono size={10} color={palette.red[300]}>
                {result.error}
              </Mono>
            ) : null}
            {result.logs.map((l, i) => (
              <Mono key={i} size={9.5} color="#c9c3b5">
                {String(l.atMs).padStart(5, ' ')}ms {l.line}
              </Mono>
            ))}
          </View>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}
