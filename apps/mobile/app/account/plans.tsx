import {
  CLOSED_BETA,
  PLAN_TIERS,
  resolveCurrentTier,
  tierPricePerMonth,
  tierPriceTotal,
  type PlanTierConfig,
} from '@llamatrade/core/billing/planTiers';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, Linking, View } from 'react-native';

import { webAppUrl } from '../../src/net/config';
import { useBillingStore } from '../../src/stores/billing';
import { makeStyles } from '../../src/theme';
import { Button, Card, Pill, Screen, Segmented, Text, type Segment } from '../../src/ui';

type Cycle = 'monthly' | 'yearly';
const CYCLE_OPTIONS: readonly Segment<Cycle>[] = [
  { key: 'monthly', label: 'Monthly' },
  { key: 'yearly', label: 'Yearly' },
];

const back = { label: 'Account', onPress: () => (router.canGoBack() ? router.back() : router.replace('/account')) };

export default function PlansScreen() {
  const s = useStyles();
  const { subscription, loaded, fetch, fetchPlans, downgradeToFree } = useBillingStore();
  const [cycle, setCycle] = useState<Cycle>('monthly');
  const yearly = cycle === 'yearly';

  useEffect(() => {
    if (!loaded) fetch();
    fetchPlans();
  }, [loaded, fetch, fetchPlans]);

  const currentTier = resolveCurrentTier(subscription) ?? 'free';

  const doDowngrade = () => {
    Alert.alert(
      'Switch to Free',
      'Paid features end at the close of your billing period. Payment methods are managed on the web.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Switch to Free',
          style: 'destructive',
          onPress: async () => {
            try {
              await downgradeToFree();
              Alert.alert('Plan updated', "You're on the Free plan.");
            } catch (e) {
              Alert.alert("Couldn't switch", e instanceof Error ? e.message : 'Please try again on the web.');
            }
          },
        },
      ],
    );
  };

  const openWeb = () => {
    Linking.openURL(`${webAppUrl}/billing`).catch(() => Alert.alert("Couldn't open the web app", webAppUrl));
  };

  return (
    <Screen title="Plans" back={back}>
      <Segmented options={CYCLE_OPTIONS} value={cycle} onChange={setCycle} />

      {PLAN_TIERS.map((tier) => (
        <PlanCard
          key={tier.key}
          tier={tier}
          yearly={yearly}
          isCurrent={tier.key === currentTier}
          onDowngrade={doDowngrade}
          onManageWeb={openWeb}
        />
      ))}

      <Text variant="small" tone="fg3" style={s.footer}>
        {CLOSED_BETA ? 'No charge during the closed beta. ' : ''}Manage billing on the web.
      </Text>
    </Screen>
  );
}

function PlanCard({
  tier,
  yearly,
  isCurrent,
  onDowngrade,
  onManageWeb,
}: {
  tier: PlanTierConfig;
  yearly: boolean;
  isCurrent: boolean;
  onDowngrade: () => void;
  onManageWeb: () => void;
}) {
  const s = useStyles();
  const price = tierPricePerMonth(tier, yearly);
  const priceNote =
    yearly && tier.monthlyPrice > 0
      ? `Billed yearly, $${tierPriceTotal(tier, true).toLocaleString('en-US')} a year`
      : tier.priceNote;

  return (
    <Card selected={isCurrent} style={s.card}>
      <View style={s.head}>
        <Text variant="subhead">{tier.name}</Text>
        {isCurrent ? <Pill label="Your plan" tone="accent" /> : null}
        <Text variant="numStrong" style={s.price}>
          ${price}
          <Text variant="numSmall" tone="fg3">/mo</Text>
        </Text>
      </View>
      <Text variant="small" tone="fg2">{tier.tagline}</Text>
      <Text variant="caption" tone="fg3">{priceNote}</Text>

      <View style={s.features}>
        {tier.features.map((row) => (
          <View key={row.label} style={s.feature}>
            <Text variant="small" tone="fg3">{row.label}</Text>
            <Text variant="numSmall">{row.value}</Text>
          </View>
        ))}
      </View>

      {isCurrent ? null : tier.key === 'free' ? (
        <Button label="Switch to Free" variant="secondary" size="sm" onPress={onDowngrade} />
      ) : (
        <Button label="Manage on the web" variant="secondary" size="sm" onPress={onManageWeb} />
      )}
    </Card>
  );
}

const useStyles = makeStyles((t) => ({
  card: { gap: 6 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  price: { marginLeft: 'auto' },
  features: { marginTop: 6, marginBottom: 4, borderTopWidth: 1, borderColor: t.c.line, paddingTop: 6, gap: 4 },
  feature: { flexDirection: 'row', justifyContent: 'space-between', gap: 10 },
  footer: { textAlign: 'center' },
}));
