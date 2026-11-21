import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { router, useLocalSearchParams } from 'expo-router';
import { KeyRound } from 'lucide-react-native';
import { useEffect, useState } from 'react';
import { Alert, View } from 'react-native';

import { AlpacaBadge, CheckLine } from '../../src/account/parts';
import { makeStyles, useTheme } from '../../src/theme';
import { Button, Card, Field, LogoMark, Notice, Screen, Segmented, Text, type Segment } from '../../src/ui';

type Env = 'paper' | 'live';
const ENV_OPTIONS: readonly Segment<Env>[] = [
  { key: 'paper', label: '1  Paper' },
  { key: 'live', label: '2  Live' },
];

const back = { label: 'Broker', onPress: () => (router.canGoBack() ? router.back() : router.replace('/account/broker')) };

export default function ConnectBrokerScreen() {
  const { c } = useTheme();
  const s = useStyles();
  const params = useLocalSearchParams<{ env?: string }>();
  const { credentials, connecting, error, fetch, connect, clearError } = useBrokerStore();

  const [env, setEnv] = useState<Env>(params.env === 'live' ? 'live' : 'paper');
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');
  const [missing, setMissing] = useState<'key' | 'secret' | null>(null);

  useEffect(() => {
    fetch();
  }, [fetch]);

  const existing = credentials.find((cr) => cr.isPaper === (env === 'paper'));
  const paperConnected = credentials.some((cr) => cr.isPaper);

  const connectKeys = async () => {
    const ok = await connect({ name: '', apiKey: apiKey.trim(), apiSecret: apiSecret.trim(), isPaper: env === 'paper' });
    if (ok) {
      setApiKey('');
      setApiSecret('');
      Alert.alert(env === 'paper' ? 'Alpaca paper connected' : 'Alpaca live connected', env === 'paper' ? 'You can start paper sessions now.' : 'Live sessions trade on this account only when you start them.');
      router.replace('/account/broker');
    }
  };

  const submit = () => {
    clearError();
    if (!apiKey.trim()) return setMissing('key');
    if (!apiSecret.trim()) return setMissing('secret');
    setMissing(null);
    if (env === 'paper') {
      connectKeys();
      return;
    }
    Alert.alert(
      'Connect a live account',
      'Live keys place real orders with real money in your Alpaca account. Strategies only trade on it when you start a live session.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Connect live', onPress: () => connectKeys() },
      ],
    );
  };

  return (
    <Screen title="Connect Alpaca" back={back} art="bold" artSeed="account-connect">
      <View style={s.pair}>
        <LogoMark size={30} bold />
        <View style={s.pairLine} />
        <AlpacaBadge size={30} />
      </View>

      <Segmented options={ENV_OPTIONS} value={env} onChange={(k) => { setEnv(k); clearError(); }} fill />

      {env === 'live' ? (
        <Card style={s.card}>
          <Text variant="subhead">Live is its own step</Text>
          <Text variant="small" tone="fg2">
            A separate key pair from Alpaca&apos;s live dashboard. Connecting it moves nothing: paper sessions stay on paper, and a session only trades live when you start it on live.
          </Text>
          {!paperConnected ? <Text variant="small" tone="fg3">Most people connect paper first and run a session there.</Text> : null}
        </Card>
      ) : null}

      <Card style={[s.card, s.cardMuted]}>
        <View style={s.cardHead}>
          <AlpacaBadge size={20} faded />
          <Text variant="bodyStrong" style={s.flex}>Approve on Alpaca</Text>
          <Text variant="caption" tone="fg3">On the web</Text>
        </View>
        <Text variant="small" tone="fg2">Sign in on Alpaca&apos;s site and choose Allow, with no keys to copy. This works from the web app for now.</Text>
      </Card>

      <Card style={s.card}>
        <View style={s.cardHead}>
          <KeyRound color={c.fg2} size={18} strokeWidth={1.7} />
          <Text variant="bodyStrong" style={s.flex}>Paste an API key pair</Text>
        </View>
        <Text variant="small" tone="fg2">From Alpaca&apos;s {env} dashboard, under API keys.</Text>
        <Field label="API key ID" value={apiKey} onChange={(v) => { setApiKey(v); setMissing(null); }} placeholder={env === 'paper' ? 'PK…' : 'AK…'} mono error={missing === 'key' ? 'Paste the key ID from Alpaca.' : null} />
        <Field label="Secret key" value={apiSecret} onChange={(v) => { setApiSecret(v); setMissing(null); }} placeholder="Shown once in Alpaca" secure mono error={missing === 'secret' ? 'Paste the secret that came with the key ID.' : null} />
      </Card>

      <View style={s.checks}>
        <CheckLine ok label="Place orders and read balances" />
        <CheckLine ok={false} label="Move money or see bank details" />
      </View>

      {existing ? (
        <Notice tone="neutral" detail={`Alpaca ${env} is already connected. New keys are added as a second ${env} pair, and you can remove the old one on the Broker page.`} />
      ) : null}
      {error ? <Notice title="Alpaca didn't accept those keys." detail={error} /> : null}

      <Button label={env === 'paper' ? 'Connect paper' : 'Connect live'} onPress={submit} loading={connecting} />
      <Text variant="caption" tone="fg3" style={s.center}>
        Keys are checked with Alpaca, stored encrypted and only sent over TLS.
      </Text>
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  pair: { flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 10, marginVertical: 4 },
  pairLine: { width: 48, height: 1, borderTopWidth: 1, borderStyle: 'dashed', borderColor: t.c.lineStrong },
  card: { gap: 10 },
  cardMuted: { opacity: 0.85 },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  checks: { gap: 8, paddingHorizontal: 2 },
  center: { textAlign: 'center' },
}));
