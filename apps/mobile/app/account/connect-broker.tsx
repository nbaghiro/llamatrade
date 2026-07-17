import { router } from 'expo-router';
import { Lock, Warehouse, X } from 'lucide-react-native';
import { useEffect, useState } from 'react';
import { Alert, Pressable, View } from 'react-native';

import { Field } from '../../src/auth/ui';
import { useBillingStore } from '../../src/stores/billing';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { palette } from '../../src/theme';
import { Badge, Body, Button, Card, Display, Label, Mono, SegmentedToggle } from '../../src/ui';
import { Screen } from '../../src/ui/Screen';

type Env = 'paper' | 'live';
const ENV_OPTIONS = [
  { key: 'paper', label: 'Paper' },
  { key: 'live', label: 'Live' },
];

export default function ConnectBrokerScreen() {
  const { credentials, connecting, error, fetch, connect, remove, clearError } = useBrokerStore();
  const subscription = useBillingStore((s) => s.subscription);
  const canLive = (subscription?.plan?.maxLiveSessions ?? 0) > 0;

  const [env, setEnv] = useState<Env>('paper');
  const [name, setName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');

  useEffect(() => {
    void fetch();
  }, [fetch]);

  // If the plan can't trade live, keep the toggle on paper.
  useEffect(() => {
    if (!canLive && env === 'live') setEnv('paper');
  }, [canLive, env]);

  const submit = async () => {
    clearError();
    if (!apiKey.trim() || !apiSecret.trim()) {
      Alert.alert('Missing keys', 'Enter both your API key ID and secret key.');
      return;
    }
    const ok = await connect({
      name,
      apiKey: apiKey.trim(),
      apiSecret: apiSecret.trim(),
      isPaper: env === 'paper',
    });
    if (ok) {
      setApiKey('');
      setApiSecret('');
      setName('');
      Alert.alert('Broker connected', `Your ${env} Alpaca account is linked.`);
    }
  };

  const confirmRemove = (id: string, label: string) => {
    Alert.alert('Remove credentials', `Disconnect “${label}”?`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: () => void remove(id) },
    ]);
  };

  return (
    <Screen title="Connect Broker" onBack={() => router.back()}>
      {/* Hero */}
      <View
        style={{
          backgroundColor: palette.ink,
          borderWidth: 2,
          borderColor: palette.ink,
          padding: 18,
          alignItems: 'center',
          gap: 9,
        }}
      >
        <View
          style={{
            width: 52,
            height: 52,
            borderWidth: 2,
            borderColor: palette.orange[500],
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <Warehouse color={palette.orange[500]} size={26} strokeWidth={2.5} />
        </View>
        <Display size={22} color={palette.bone}>
          Link Alpaca
        </Display>
        <Mono
          size={10}
          color="rgba(251,248,241,0.6)"
          style={{ textAlign: 'center', letterSpacing: 0.5, lineHeight: 15 }}
        >
          THE EXACT STRATEGY YOU BACKTEST IS WHAT TRADES. BRING YOUR OWN BROKER KEYS.
        </Mono>
      </View>

      {/* Environment */}
      <View style={{ gap: 6 }}>
        <SegmentedToggle
          options={ENV_OPTIONS}
          value={env}
          onChange={(k) => setEnv(k as Env)}
          disabledKeys={canLive ? [] : ['live']}
        />
        {!canLive ? (
          <Pressable
            onPress={() => router.push('/account/plans')}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}
          >
            <Lock color={palette.gray[500]} size={12} strokeWidth={2.5} />
            <Mono size={9} color={palette.gray[600]} style={{ letterSpacing: 0.5 }}>
              LIVE TRADING REQUIRES A PRO PLAN · VIEW PLANS →
            </Mono>
          </Pressable>
        ) : null}
      </View>

      {/* Keys */}
      <View style={{ gap: 11 }}>
        <Field label="Label (optional)" value={name} onChange={setName} placeholder="My Alpaca account" autoCapitalizeWords />
        <Field label="API Key ID" value={apiKey} onChange={setApiKey} placeholder="PK…" />
        <Field label="Secret Key" value={apiSecret} onChange={setApiSecret} placeholder="••••••••••••••••" secure />
      </View>

      {/* Security note */}
      <View
        style={{
          flexDirection: 'row',
          gap: 8,
          backgroundColor: palette.green[50],
          borderWidth: 2,
          borderColor: palette.green[500],
          padding: 11,
        }}
      >
        <Lock color={palette.green[600]} size={14} strokeWidth={2.5} style={{ marginTop: 1 }} />
        <Mono size={10} color={palette.green[700]} style={{ flex: 1, lineHeight: 15 }}>
          Keys are validated with Alpaca, encrypted at rest, and sent only over TLS — never stored in plaintext.
        </Mono>
      </View>

      {error ? (
        <Card style={{ backgroundColor: palette.red[50], borderColor: palette.red[500] }}>
          <Mono size={10} color={palette.red[600]}>
            {error}
          </Mono>
        </Card>
      ) : null}

      <Button label="Connect & Verify →" onPress={submit} loading={connecting} />

      {/* Connected credentials */}
      {credentials.length ? (
        <View style={{ gap: 7, marginTop: 6 }}>
          <Label style={{ marginLeft: 2 }}>Connected</Label>
          {credentials.map((c) => (
            <Card key={c.id} style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
              <View style={{ flex: 1 }}>
                <Body size={13} style={{ fontWeight: '700' }} numberOfLines={1}>
                  {c.name || 'Alpaca account'}
                </Body>
                <Label style={{ marginTop: 2 }}>{c.apiKeyPrefix}••••</Label>
              </View>
              <Badge label={c.isPaper ? 'Paper' : 'Live'} variant={c.isPaper ? 'gray' : 'green'} />
              <Pressable onPress={() => confirmRemove(c.id, c.name || 'Alpaca account')} hitSlop={8}>
                <X color={palette.gray[500]} size={18} strokeWidth={2.5} />
              </Pressable>
            </Card>
          ))}
        </View>
      ) : null}
    </Screen>
  );
}
