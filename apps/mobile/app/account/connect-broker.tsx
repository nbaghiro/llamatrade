import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert } from 'react-native';

import { makeStyles } from '../../src/theme';
import { Button, Card, Field, ListRow, Notice, Screen, Segmented, StatusMark, Text, type Segment } from '../../src/ui';

type Env = 'paper' | 'live';
const ENV_OPTIONS: readonly Segment<Env>[] = [
  { key: 'paper', label: 'Paper' },
  { key: 'live', label: 'Live' },
];

const back = { label: 'Account', onPress: () => (router.canGoBack() ? router.back() : router.replace('/account')) };

export default function ConnectBrokerScreen() {
  const s = useStyles();
  const { credentials, connecting, error, fetch, connect, remove, clearError } = useBrokerStore();

  const [env, setEnv] = useState<Env>('paper');
  const [name, setName] = useState('');
  const [apiKey, setApiKey] = useState('');
  const [apiSecret, setApiSecret] = useState('');

  useEffect(() => {
    fetch();
  }, [fetch]);

  const connectKeys = async () => {
    const ok = await connect({ name, apiKey: apiKey.trim(), apiSecret: apiSecret.trim(), isPaper: env === 'paper' });
    if (ok) {
      setApiKey('');
      setApiSecret('');
      setName('');
      Alert.alert('Connected', `Your Alpaca ${env} account is linked.`);
    }
  };

  const submit = () => {
    clearError();
    if (!apiKey.trim() || !apiSecret.trim()) {
      Alert.alert('Missing keys', 'Enter both your API key ID and secret key.');
      return;
    }
    if (env === 'paper') {
      connectKeys();
      return;
    }
    Alert.alert(
      'Connect a live account',
      'Live keys place real orders with real money in your Alpaca account. Strategies only trade on it when you start a live session.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Connect live account', onPress: () => connectKeys() },
      ],
    );
  };

  const confirmRemove = (id: string, label: string) => {
    Alert.alert('Remove credentials', `Disconnect ${label}? Sessions on this account stop placing orders.`, [
      { text: 'Cancel', style: 'cancel' },
      { text: 'Remove', style: 'destructive', onPress: () => remove(id) },
    ]);
  };

  return (
    <Screen title="Connect broker" back={back}>
      <Text variant="small" tone="fg2" style={s.intro}>
        Paste your Alpaca paper or live keys. Live sessions need a paid plan.
      </Text>

      {credentials.map((cred) => (
        <Card key={cred.id} style={s.rows}>
          <ListRow
            label={<Text variant="bodyStrong" numberOfLines={1}>{cred.name || (cred.isPaper ? 'Alpaca paper' : 'Alpaca live')}</Text>}
            right={<StatusMark state="running" label="Connected" />}
          />
          <ListRow label="Key" right={<Text variant="numSmall">{cred.apiKeyPrefix}••••</Text>} />
          <ListRow label="Environment" value={cred.isPaper ? 'Paper' : 'Live'} last />
        </Card>
      ))}

      <Segmented options={ENV_OPTIONS} value={env} onChange={setEnv} />

      <Field label="Label (optional)" value={name} onChange={setName} placeholder="My Alpaca account" autoCapitalizeWords />
      <Field label="API key ID" value={apiKey} onChange={setApiKey} placeholder="PK..." mono />
      <Field label="Secret key" value={apiSecret} onChange={setApiSecret} placeholder="Your secret key" secure mono />

      <Text variant="caption" tone="fg3">
        Keys are checked with Alpaca, encrypted at rest and only sent over TLS.
      </Text>

      {env === 'live' ? (
        <Notice tone="neutral" detail="Live keys trade real money from your Alpaca account." />
      ) : null}

      {error ? <Notice title="Couldn't connect." detail={error} /> : null}

      <Button label="Connect and verify" onPress={submit} loading={connecting} />

      {credentials.map((cred) => (
        <Button
          key={cred.id}
          label={credentials.length > 1 ? `Remove ${cred.name || cred.apiKeyPrefix}` : 'Remove credentials'}
          variant="secondary"
          onPress={() => confirmRemove(cred.id, cred.name || 'this Alpaca account')}
        />
      ))}

    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  intro: { marginTop: -8 },
  rows: { paddingVertical: 2 },
}));
