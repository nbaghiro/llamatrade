import type { AlpacaCredentialsListItem } from '@llamatrade/core/proto/auth_pb';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { router } from 'expo-router';
import { Alert, View } from 'react-native';

import { etTime, problemText, type AccountKind, type AccountProblem } from '../../src/account/health';
import { AlpacaBadge, CheckLine, StateText } from '../../src/account/parts';
import { useAccountSummary } from '../../src/account/useAccountSummary';
import { makeStyles } from '../../src/theme';
import { Button, Card, Loading, Notice, Screen, Text } from '../../src/ui';

const back = { label: 'Account', onPress: () => (router.canGoBack() ? router.back() : router.replace('/account')) };

const LABEL: Record<AccountKind, string> = { paper: 'Paper', live: 'Live' };

const connect = (env: AccountKind) => router.push({ pathname: '/account/connect-broker', params: { env } });

function ProblemStrip({ problem }: { problem: AccountProblem }) {
  const s = useStyles();
  const t = problemText(problem);
  const parts: [string, string][] = [
    ['What happened', t.happened],
    ['What it affects', t.affects],
    ['What to do', `Paste a new ${problem.kind} key pair from Alpaca. Sessions pick the new keys up at their next run.`],
  ];
  return (
    <View style={s.strip}>
      {parts.map(([k, v]) => (
        <View key={k} style={s.stripPart}>
          <Text variant="label" tone="risk">{k}</Text>
          <Text variant="small" tone="fg2">{v}</Text>
        </View>
      ))}
    </View>
  );
}

function AccountPanel({
  kind,
  cred,
  problem,
  running,
}: {
  kind: AccountKind;
  cred: AlpacaCredentialsListItem;
  problem: AccountProblem | undefined;
  running: number;
}) {
  const s = useStyles();
  const lastCheck = useBrokerStore((st) => st.lastCheck);
  const remove = useBrokerStore((st) => st.remove);
  const checked = lastCheck && (kind === 'paper') === lastCheck.isPaper && lastCheck.valid ? etTime(lastCheck.at) : null;

  const confirmRemove = () =>
    Alert.alert(
      `Remove the ${kind} keys`,
      running > 0
        ? `${running === 1 ? 'One running session uses' : `${running} running sessions use`} this account. Stop them first, or they can't place orders.`
        : 'You can connect the account again at any time.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Remove',
          style: 'destructive',
          onPress: async () => {
            const ok = await remove(cred.id);
            if (!ok) Alert.alert("The keys weren't removed", useBrokerStore.getState().error ?? 'Please try again.');
          },
        },
      ],
    );

  return (
    <Card style={[s.panel, problem ? s.panelRisk : null]}>
      <View style={s.head}>
        <AlpacaBadge size={22} />
        <Text variant="subhead">{LABEL[kind]}</Text>
        <Text variant="numSmall" tone="fg3" style={s.flex} numberOfLines={1}>
          {cred.accountNumber || `${cred.apiKeyPrefix}••••`}
        </Text>
        <StateText label={problem ? problemText(problem).short : 'Connected'} risk={!!problem} />
      </View>
      {problem ? (
        <>
          <ProblemStrip problem={problem} />
          <Button label={`Replace the ${kind} keys`} onPress={() => connect(kind)} size="sm" />
        </>
      ) : (
        <View style={s.checks}>
          <CheckLine ok label={checked ? 'Keys accepted by Alpaca' : 'Keys stored and switched on'} detail={checked ?? undefined} />
          <CheckLine ok label={running === 1 ? '1 session running on this account' : `${running} sessions running on this account`} />
          <Text variant="caption" tone="fg3">
            {checked ? 'Checked from this phone.' : 'The app keeps no record of when Alpaca last checked these keys.'}
          </Text>
        </View>
      )}
      <Button label="Remove these keys" variant="secondary" size="sm" onPress={confirmRemove} />
    </Card>
  );
}

function NotConnected({ kind }: { kind: AccountKind }) {
  const s = useStyles();
  return (
    <Card style={[s.panel, s.ghost]}>
      <View style={s.head}>
        <AlpacaBadge size={22} faded />
        <Text variant="subhead" style={s.flex}>{LABEL[kind]}</Text>
        <StateText label="Not connected" />
      </View>
      <Text variant="small" tone="fg2">
        {kind === 'live'
          ? 'Real money. Connect it when you want to start a session on live. Paper sessions stay on paper.'
          : 'Simulated money on Alpaca. Paper sessions need it; backtests run without it.'}
      </Text>
      <Button label={`Connect ${kind}`} variant="secondary" size="sm" onPress={() => connect(kind)} />
    </Card>
  );
}

export default function BrokerScreen() {
  const credentials = useBrokerStore((st) => st.credentials);
  const error = useBrokerStore((st) => st.error);
  const { health, sessions, brokerLoaded } = useAccountSummary();

  return (
    <Screen title="Broker" back={back} art="bold" artSeed="account-broker">
      {!brokerLoaded ? <Loading label="Loading your Alpaca accounts" /> : null}
      {error ? <Notice detail={error} /> : null}
      {brokerLoaded
        ? (['paper', 'live'] as const).map((kind) => {
            const cred = credentials.find((cr) => (kind === 'paper') === cr.isPaper);
            if (!cred) return <NotConnected key={kind} kind={kind} />;
            return (
              <AccountPanel
                key={kind}
                kind={kind}
                cred={cred}
                problem={health.problems.find((p) => p.kind === kind)}
                running={sessions.filter((se) => se.kind === kind && se.running).length}
              />
            );
          })
        : null}
      <Text variant="caption" tone="fg3">
        Keys are stored encrypted. The secret is never shown again.
      </Text>
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  panel: { gap: 12 },
  panelRisk: { borderColor: t.c.riskLine },
  ghost: { borderStyle: 'dashed', borderColor: t.c.lineStrong },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  checks: { gap: 8 },
  strip: { borderRadius: 8, borderWidth: 1, borderColor: t.c.riskLine, backgroundColor: t.c.riskSoft, padding: 12, gap: 10 },
  stripPart: { gap: 2 },
}));
