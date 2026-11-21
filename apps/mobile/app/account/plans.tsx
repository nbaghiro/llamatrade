import {
  PLAN_TIER_BY_KEY,
  PLAN_TIERS,
  resolveCurrentTier,
  tierPricePerMonth,
  tierPriceTotal,
  type PlanTierConfig,
} from '@llamatrade/core/billing/planTiers';
import { BillingInterval, InvoiceStatus, PlanTier, SubscriptionStatus, type Subscription } from '@llamatrade/core/proto/billing_pb';
import type { Money, Timestamp } from '@llamatrade/core/proto/common_pb';
import { useBillingStore } from '@llamatrade/core/stores/billing';
import { router } from 'expo-router';
import { CreditCard, FileText } from 'lucide-react-native';
import { useCallback, useEffect, useState } from 'react';
import { Alert, Linking, View } from 'react-native';

import { ForecastMeter } from '../../src/account/parts';
import { resetLabel, usageRow, type UsageRow } from '../../src/account/usage';
import { webAppUrl } from '../../src/net/config';
import { makeStyles, useTheme } from '../../src/theme';
import { Button, Card, Loading, Pill, Screen, SectionLabel, Segmented, Text, type Segment } from '../../src/ui';

type Cycle = 'monthly' | 'yearly';
const CYCLE_OPTIONS: readonly Segment<Cycle>[] = [
  { key: 'monthly', label: 'Monthly' },
  { key: 'yearly', label: 'Yearly' },
];

const back = { label: 'Account', onPress: () => (router.canGoBack() ? router.back() : router.replace('/account')) };

const moneyNum = (m?: Money) => (m?.amount ? parseFloat(m.amount) || 0 : 0);
const fmtDay = (ts?: Timestamp) =>
  ts?.seconds ? new Date(Number(ts.seconds) * 1000).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' }) : '';
const usd = (n: number) => `$${n.toLocaleString('en-US', { minimumFractionDigits: n % 1 ? 2 : 0, maximumFractionDigits: 2 })}`;
const MONTH = (d: Date) => d.toLocaleDateString('en-US', { month: 'long' });

function planLine(sub: Subscription | null, tier: PlanTierConfig): string {
  if (!sub) return 'No subscription. Backtests and paper sessions work on Free.';
  if (sub.isBeta) return `No charge during the closed beta. Normally ${usd(tier.monthlyPrice)} a month, and nothing is billed until you choose a paid plan.`;
  const price = moneyNum(sub.currentPrice) || tier.monthlyPrice;
  if (sub.cancelAtPeriodEnd) return `${usd(price)} a month. Ends ${fmtDay(sub.currentPeriodEnd)}.`;
  if (sub.status === SubscriptionStatus.TRIALING && sub.trialEnd) return `Trial ends ${fmtDay(sub.trialEnd)}, then ${usd(price)} a month.`;
  if (sub.status === SubscriptionStatus.PAST_DUE) return `${usd(price)} a month. The last payment failed; update the card on the web.`;
  return price > 0 ? `${usd(price)} a month. Renews ${fmtDay(sub.currentPeriodEnd)}.` : 'Free.';
}

function UsageLine({ row }: { row: UsageRow }) {
  const s = useStyles();
  const risk = row.atLimit || row.willPass;
  return (
    <View style={s.usage}>
      <View style={s.usageHead}>
        <Text variant="body" style={s.flex}>{row.label}</Text>
        <Text variant="num" tone={row.atLimit ? 'risk' : 'fg'}>{row.figure}</Text>
      </View>
      {row.limit > 0 ? <ForecastMeter fraction={row.fraction} forecast={row.forecastFraction} risk={risk} /> : null}
      {row.forecastNote ? (
        <Text variant="caption" tone={row.willPass ? 'risk' : 'fg3'}>
          {row.forecastNote}{row.willPass ? ', past the limit' : ''}
        </Text>
      ) : null}
    </View>
  );
}

export default function PlansScreen() {
  const { c } = useTheme();
  const s = useStyles();
  const subscription = useBillingStore((st) => st.subscription);
  const plans = useBillingStore((st) => st.plans);
  const usageCounts = useBillingStore((st) => st.usageCounts);
  const paymentMethods = useBillingStore((st) => st.paymentMethods);
  const invoices = useBillingStore((st) => st.invoices);
  const loaded = useBillingStore((st) => st.loaded);
  const fetchSubscription = useBillingStore((st) => st.fetchSubscription);
  const fetchPlans = useBillingStore((st) => st.fetchPlans);
  const fetchUsageCounts = useBillingStore((st) => st.fetchUsageCounts);
  const fetchPaymentMethods = useBillingStore((st) => st.fetchPaymentMethods);
  const fetchInvoices = useBillingStore((st) => st.fetchInvoices);
  const updateSubscription = useBillingStore((st) => st.updateSubscription);
  const createSubscription = useBillingStore((st) => st.createSubscription);
  const [cycle, setCycle] = useState<Cycle>('monthly');
  const [refreshing, setRefreshing] = useState(false);

  const load = useCallback(
    () =>
      Promise.all([fetchSubscription(), fetchPlans(), fetchUsageCounts(), fetchPaymentMethods(), fetchInvoices()]).then(() => undefined),
    [fetchSubscription, fetchPlans, fetchUsageCounts, fetchPaymentMethods, fetchInvoices],
  );

  useEffect(() => {
    load().catch(() => undefined);
  }, [load]);

  const tierKey = resolveCurrentTier(subscription) ?? 'free';
  const tier = PLAN_TIER_BY_KEY[tierKey];
  const now = new Date();
  const rows = usageCounts
    ? [
        usageRow({ label: 'Backtests', used: usageCounts.backtests, limit: tier.limits.backtestsPerMonth, monthly: true }, now),
        usageRow({ label: 'Copilot messages', used: usageCounts.copilotMessages, limit: tier.limits.copilotMessages, monthly: true }, now),
        usageRow({ label: 'Strategies', used: usageCounts.strategies, limit: tier.limits.strategies, monthly: false }, now),
        usageRow({ label: 'Live sessions', used: usageCounts.liveSessions, limit: tier.limits.liveSessions, monthly: false }, now),
      ]
    : null;
  const card = paymentMethods.find((p) => p.isDefault) ?? paymentMethods[0];

  const openWeb = () => {
    Linking.openURL(`${webAppUrl}/billing`).catch(() => Alert.alert("The web app couldn't be opened", webAppUrl));
  };

  const switchToFree = () => {
    const free = plans.find((p) => p.tier === PlanTier.FREE);
    if (!free) {
      Alert.alert('Free isn’t available here', 'Change your plan on the web.');
      return;
    }
    Alert.alert('Switch to Free', 'Paid features end at the close of the billing period. Running live sessions keep trading until then.', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Switch to Free',
        style: 'destructive',
        onPress: async () => {
          try {
            if (subscription) await updateSubscription(free.id, BillingInterval.MONTHLY, true);
            else await createSubscription(free.id, BillingInterval.MONTHLY, '');
            Alert.alert('Plan updated', "You're on the Free plan.");
          } catch (e) {
            Alert.alert("The plan wasn't changed", e instanceof Error ? e.message : 'Please try again on the web.');
          }
        },
      },
    ]);
  };

  return (
    <Screen
      title="Plan and usage"
      back={back}
      art="bold"
      artSeed="account-plan"
      refreshing={refreshing}
      onRefresh={() => {
        setRefreshing(true);
        load().finally(() => setRefreshing(false));
      }}
    >
      {!loaded.subscription ? (
        <Loading label="Loading your plan" />
      ) : (
        <Card style={s.plan}>
          <View style={s.planHead}>
            <Text variant="heading">{tier.name}</Text>
            {subscription?.isBeta ? <Pill label="Beta" tone="accent" /> : null}
            <View style={s.flex} />
            <Text variant="numLarge">{subscription?.isBeta ? '$0' : usd(moneyNum(subscription?.currentPrice) || tier.monthlyPrice)}</Text>
          </View>
          <Text variant="small" tone="fg2">{planLine(subscription, tier)}</Text>
        </Card>
      )}

      <View style={s.secHead}>
        <SectionLabel>{MONTH(now)}</SectionLabel>
        <Text variant="label" tone="fg3">Resets {resetLabel(now)}</Text>
      </View>
      <Card style={s.usageCard}>
        {rows ? rows.map((r) => <UsageLine key={r.label} row={r} />) : <Loading label="Counting this month's usage" />}
        {rows ? <Text variant="caption" tone="fg3">The dashed stretch is where the month is heading at the pace so far.</Text> : null}
      </Card>

      <Card style={s.rows}>
        <View style={[s.row, s.divider]}>
          <CreditCard color={c.fg3} size={18} strokeWidth={1.7} />
          <Text variant="body" style={s.flex}>
            {card ? `${(card.cardBrand || 'Card').replace(/^\w/, (ch) => ch.toUpperCase())} •••• ${card.cardLast4}` : 'No card on file'}
          </Text>
          <Text variant="small" tone="fg3">{card ? 'Default' : subscription?.isBeta ? 'Not needed yet' : 'Add on the web'}</Text>
        </View>
        {invoices.length === 0 ? (
          <View style={s.row}>
            <FileText color={c.fg3} size={18} strokeWidth={1.7} />
            <Text variant="body" style={s.flex}>No invoices yet</Text>
          </View>
        ) : (
          invoices.slice(0, 3).map((inv, i, list) => (
            <View key={inv.id} style={[s.row, i < list.length - 1 ? s.divider : null]}>
              <FileText color={c.fg3} size={18} strokeWidth={1.7} />
              <View style={s.flex}>
                <Text variant="body" numberOfLines={1}>{inv.items[0]?.description || 'Subscription'}</Text>
                <Text variant="caption" tone="fg3">{fmtDay(inv.paidAt ?? inv.periodStart)}</Text>
              </View>
              <View style={s.end}>
                <Text variant="numSmall">{usd(moneyNum(inv.amountPaid ?? inv.amount))}</Text>
                <Text variant="caption" tone={inv.status === InvoiceStatus.PAID ? 'fg3' : 'risk'}>{inv.status === InvoiceStatus.PAID ? 'Paid' : 'Due'}</Text>
              </View>
            </View>
          ))
        )}
      </Card>

      <SectionLabel>Compare plans</SectionLabel>
      <Segmented options={CYCLE_OPTIONS} value={cycle} onChange={setCycle} fill />
      {PLAN_TIERS.map((t) => (
        <PlanCard
          key={t.key}
          tier={t}
          yearly={cycle === 'yearly'}
          isCurrent={t.key === tierKey}
          onFree={switchToFree}
          onWeb={openWeb}
        />
      ))}
      <Text variant="caption" tone="fg3" style={s.center}>Paid plans and payment methods are managed on the web.</Text>
    </Screen>
  );
}

function PlanCard({ tier, yearly, isCurrent, onFree, onWeb }: { tier: PlanTierConfig; yearly: boolean; isCurrent: boolean; onFree: () => void; onWeb: () => void }) {
  const s = useStyles();
  const price = tierPricePerMonth(tier, yearly);
  const note = yearly && tier.monthlyPrice > 0 ? `Billed yearly, $${tierPriceTotal(tier, true).toLocaleString('en-US')} a year` : tier.priceNote;
  return (
    <Card selected={isCurrent} style={s.tier}>
      <View style={s.planHead}>
        <Text variant="subhead">{tier.name}</Text>
        {isCurrent ? <Pill label="Your plan" tone="accent" /> : null}
        <View style={s.flex} />
        <Text variant="numStrong">
          ${price}
          <Text variant="numSmall" tone="fg3"> a month</Text>
        </Text>
      </View>
      <Text variant="small" tone="fg2">{tier.tagline}</Text>
      <Text variant="caption" tone="fg3">{note}</Text>
      <View style={s.features}>
        {tier.features.map((row) => (
          <View key={row.label} style={s.feature}>
            <Text variant="small" tone="fg3">{row.label}</Text>
            <Text variant="numSmall">{row.value}</Text>
          </View>
        ))}
      </View>
      {isCurrent ? null : tier.key === 'free' ? (
        <Button label="Switch to Free" variant="secondary" size="sm" onPress={onFree} />
      ) : (
        <Button label="Change on the web" variant="secondary" size="sm" onPress={onWeb} />
      )}
    </Card>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  plan: { gap: 8, borderColor: t.c.lineStrong, ...t.shadow.md },
  planHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  secHead: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  usageCard: { gap: 16 },
  usage: { gap: 7 },
  usageHead: { flexDirection: 'row', alignItems: 'baseline', gap: 8 },
  rows: { paddingVertical: 0 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, minHeight: 50, paddingVertical: 8 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  end: { alignItems: 'flex-end', gap: 2 },
  tier: { gap: 6 },
  features: { marginTop: 6, marginBottom: 4, borderTopWidth: 1, borderColor: t.c.line, paddingTop: 6, gap: 4 },
  feature: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
  center: { textAlign: 'center' },
}));
