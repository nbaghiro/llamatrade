import { InvoiceStatus, PlanTier, SubscriptionStatus, type Invoice, type Subscription } from '@llamatrade/core/proto/billing_pb';
import type { Money, Timestamp } from '@llamatrade/core/proto/common_pb';
import { useBrokerStore } from '@llamatrade/core/stores/broker';
import { router } from 'expo-router';
import { useEffect } from 'react';
import { View } from 'react-native';

import { useAuthStore } from '../../src/stores/auth';
import { useBillingStore } from '../../src/stores/billing';
import { makeStyles, useTheme } from '../../src/theme';
import { AppearancePicker } from '../../src/ui/AppearancePicker';
import { Button, Card, ListRow, Loading, Meter, Notice, Pill, Screen, Text } from '../../src/ui';

function moneyNum(m?: Money): number {
  return m?.amount ? parseFloat(m.amount) || 0 : 0;
}

function fmtDay(ts?: Timestamp): string {
  return ts?.seconds
    ? new Date(Number(ts.seconds) * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
    : '–';
}

function fmtUsd(n: number): string {
  return `$${n.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const TIER_LABEL: Record<PlanTier, string> = {
  [PlanTier.UNSPECIFIED]: 'Free',
  [PlanTier.FREE]: 'Free',
  [PlanTier.STARTER]: 'Starter',
  [PlanTier.PRO]: 'Pro',
};

function tierName(sub: Subscription | null): string {
  return sub?.plan?.name || TIER_LABEL[sub?.plan?.tier ?? PlanTier.FREE] || 'Free';
}

function subStatus(sub: Subscription | null): string {
  if (!sub) return 'No plan';
  if (sub.cancelAtPeriodEnd) return 'Canceling';
  switch (sub.status) {
    case SubscriptionStatus.ACTIVE:
      return 'Active';
    case SubscriptionStatus.TRIALING:
      return 'Trial';
    case SubscriptionStatus.PAST_DUE:
      return 'Past due';
    case SubscriptionStatus.PAUSED:
      return 'Paused';
    case SubscriptionStatus.CANCELED:
      return 'Canceled';
    default:
      return 'Unknown';
  }
}

function renewalLine(sub: Subscription | null): string {
  if (!sub) return '';
  if (sub.status === SubscriptionStatus.TRIALING && sub.trialEnd) return `Trial ends ${fmtDay(sub.trialEnd)}`;
  if (sub.cancelAtPeriodEnd) return `Ends ${fmtDay(sub.currentPeriodEnd)}`;
  return `Renews ${fmtDay(sub.currentPeriodEnd)}`;
}

function MeterRow({ label, used, limit }: { label: string; used: number; limit: number }) {
  const { c } = useTheme();
  const s = useStyles();
  const unlimited = limit <= 0;
  const atLimit = !unlimited && used >= limit;
  return (
    <View style={s.meter}>
      <View style={s.meterHead}>
        <Text variant="small">{label}</Text>
        <Text variant="numSmall" tone={atLimit ? 'risk' : 'fg2'}>
          {used.toLocaleString('en-US')} / {unlimited ? 'no limit' : limit.toLocaleString('en-US')}
        </Text>
      </View>
      <Meter value={unlimited ? 0 : used / limit} color={atLimit ? c.risk : undefined} />
    </View>
  );
}

function InvoiceRow({ inv, last }: { inv: Invoice; last: boolean }) {
  const paid = inv.status === InvoiceStatus.PAID;
  return (
    <ListRow
      last={last}
      label={inv.items[0]?.description || 'Subscription'}
      sub={fmtDay(inv.paidAt ?? inv.periodStart)}
      right={
        <View style={{ alignItems: 'flex-end', gap: 2 }}>
          <Text variant="numSmall">{fmtUsd(moneyNum(inv.amountPaid ?? inv.amount))}</Text>
          <Text variant="caption" tone={paid ? 'fg3' : 'risk'}>{paid ? 'Paid' : 'Due'}</Text>
        </View>
      }
    />
  );
}

export default function AccountScreen() {
  const s = useStyles();
  const user = useAuthStore((st) => st.user);
  const logout = useAuthStore((st) => st.logout);
  const { subscription, usage, paymentMethods, invoices, loading, refreshing, loaded, error, fetch } = useBillingStore();
  const credentials = useBrokerStore((st) => st.credentials);
  const fetchBroker = useBrokerStore((st) => st.fetch);

  useEffect(() => {
    fetch();
    fetchBroker();
  }, [fetch, fetchBroker]);

  const name = user ? `${user.firstName ?? ''} ${user.lastName ?? ''}`.trim() || user.email : '–';
  const plan = subscription?.plan;
  const price = moneyNum(subscription?.currentPrice) || moneyNum(plan?.monthlyPrice);
  const pm = paymentMethods.find((p) => p.isDefault) ?? paymentMethods[0];
  const broker = credentials[0];

  return (
    <Screen title="Account" refreshing={refreshing} onRefresh={() => fetch({ refresh: true })}>
      <Card style={s.rows}>
        <ListRow
          label={<Text variant="bodyStrong" numberOfLines={1}>{name}</Text>}
          right={<Text variant="small" tone="fg3" numberOfLines={1} style={s.email}>{user?.email ?? '–'}</Text>}
        />
        <ListRow
          last
          label="Broker"
          onPress={() => router.push('/account/connect-broker')}
          value={
            broker
              ? `${broker.isPaper ? 'Alpaca paper' : 'Alpaca live'}${credentials.length > 1 ? ` +${credentials.length - 1}` : ''}`
              : 'Not connected'
          }
        />
      </Card>

      {loading && !loaded ? (
        <Loading label="Loading your plan" />
      ) : (
        <>
          {error ? <Notice title="Couldn't load billing." detail={`${error} Pull down to try again.`} /> : null}

          <Card onPress={() => router.push('/account/plans')} style={s.plan}>
            <View style={s.planHead}>
              <Text variant="label" tone="fg3">Current plan</Text>
              <Pill label={subStatus(subscription)} tone="accent" />
            </View>
            <Text variant="heading">{tierName(subscription)}</Text>
            <Text variant="small" tone="fg3">
              {[price > 0 ? `${fmtUsd(price)} a month` : '', renewalLine(subscription)].filter(Boolean).join(' · ')}
            </Text>
          </Card>

          {usage && plan ? (
            <Card style={s.usage}>
              <MeterRow label="Strategies" used={usage.strategiesCreated} limit={plan.maxStrategies} />
              <MeterRow label="Backtests this month" used={usage.backtestsRun} limit={plan.maxBacktestsPerMonth} />
              <MeterRow label="Live sessions" used={usage.liveSessions} limit={plan.maxLiveSessions} />
              <MeterRow label="Copilot messages" used={Number(usage.apiCalls)} limit={-1} />
            </Card>
          ) : null}

          <Card style={s.rows}>
            <ListRow label="Plans" onPress={() => router.push('/account/plans')} />
            <ListRow
              label="Payment method"
              value={pm ? `${(pm.cardBrand || 'Card').replace(/^\w/, (ch) => ch.toUpperCase())} •••• ${pm.cardLast4}` : 'None'}
              last={invoices.length === 0}
            />
            {invoices.length ? (
              <>
                <Text variant="label" tone="fg3" style={s.historyLabel}>Billing history</Text>
                {invoices.slice(0, 3).map((inv, i, list) => (
                  <InvoiceRow key={inv.id} inv={inv} last={i === list.length - 1} />
                ))}
              </>
            ) : null}
          </Card>
        </>
      )}

      <Card>
        <Text variant="label" tone="fg3" style={s.appearanceLabel}>Appearance</Text>
        <AppearancePicker />
      </Card>

      <Button label="Log out" variant="secondary" onPress={logout} />
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  rows: { paddingVertical: 2 },
  email: { maxWidth: '55%' },
  plan: { gap: 6 },
  planHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  usage: { gap: 14 },
  meter: { gap: 6 },
  meterHead: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' },
  historyLabel: { marginTop: 10, marginBottom: 2 },
  appearanceLabel: { marginBottom: 12 },
}));
