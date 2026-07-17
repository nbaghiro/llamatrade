import {
  PLAN_TIERS,
  resolveCurrentTier,
  tierPricePerMonth,
  tierPriceTotal,
  type PlanTierConfig,
} from '@llamatrade/core/billing/planTiers';
import { router } from 'expo-router';
import { useEffect, useState } from 'react';
import { Alert, Linking, View, type ViewStyle } from 'react-native';

import { webAppUrl } from '../../src/net/config';
import { useBillingStore } from '../../src/stores/billing';
import { palette } from '../../src/theme';
import { Badge, Button, Display, Mono, SegmentedToggle } from '../../src/ui';
import { Screen } from '../../src/ui/Screen';

type Cycle = 'monthly' | 'yearly';
const CYCLE_OPTIONS = [
  { key: 'monthly', label: 'Monthly' },
  { key: 'yearly', label: 'Yearly −17%' },
];

export default function PlansScreen() {
  const { subscription, loaded, fetch, fetchPlans, downgradeToFree } = useBillingStore();
  const [cycle, setCycle] = useState<Cycle>('monthly');
  const yearly = cycle === 'yearly';

  useEffect(() => {
    if (!loaded) void fetch();
    void fetchPlans();
  }, [loaded, fetch, fetchPlans]);

  const currentTier = resolveCurrentTier(subscription) ?? 'free';

  const doDowngrade = () => {
    Alert.alert(
      'Switch to Free',
      'You’ll move to the Free plan; paid features end at the close of your billing period. Payment methods are managed on the web.',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Switch to Free',
          style: 'destructive',
          onPress: async () => {
            try {
              await downgradeToFree();
              Alert.alert('Plan updated', 'You’re on the Free plan.');
            } catch (e) {
              Alert.alert('Couldn’t switch', e instanceof Error ? e.message : 'Please try again on the web.');
            }
          },
        },
      ],
    );
  };

  const openWeb = () => {
    void Linking.openURL(`${webAppUrl}/billing`);
  };

  return (
    <Screen title="Plans" onBack={() => router.back()}>
      <SegmentedToggle options={CYCLE_OPTIONS} value={cycle} onChange={(k) => setCycle(k as Cycle)} />

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

      <Mono size={9} color={palette.gray[500]} style={{ textAlign: 'center', marginTop: 2, lineHeight: 14 }}>
        PAID PLAN CHANGES & PAYMENT METHODS ARE MANAGED ON THE WEB.
      </Mono>
    </Screen>
  );
}

/** Hard brutalist offset shadow (iOS). */
function hardShadow(color: string): ViewStyle {
  return { shadowColor: color, shadowOffset: { width: 5, height: 5 }, shadowOpacity: 1, shadowRadius: 0, elevation: 6 };
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
  const isPro = tier.key === 'pro';
  const price = tierPricePerMonth(tier, yearly);
  const priceNote =
    yearly && tier.monthlyPrice > 0
      ? `Billed yearly · $${tierPriceTotal(tier, true).toLocaleString('en-US')}/yr`
      : tier.priceNote;
  const ink = palette.ink;
  const bg = isPro ? palette.orange[500] : palette.paper;
  const subtle = isPro ? 'rgba(13,13,13,0.62)' : palette.gray[500];
  const rowBorder = isPro ? 'rgba(13,13,13,0.15)' : palette.bone2;

  return (
    <View style={[{ backgroundColor: bg, borderWidth: 2, borderColor: ink, padding: 16 }, hardShadow(ink)]}>
      {tier.badge || isCurrent ? (
        <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginBottom: 12 }}>
          {tier.badge ? <Badge label={tier.badge} variant={isPro ? 'ink' : 'gray'} /> : <View />}
          {isCurrent ? <Badge label="Your Plan" variant="ink" /> : null}
        </View>
      ) : null}

      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'flex-start' }}>
        <View style={{ flex: 1 }}>
          <Display size={24} color={ink}>
            {tier.name}
          </Display>
          <Mono size={9} color={subtle} style={{ marginTop: 3, letterSpacing: 0.5 }}>
            {tier.tagline.toUpperCase()}
          </Mono>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 2 }}>
          <Display size={30} color={ink}>
            ${price}
          </Display>
          <Mono size={10} color={subtle}>
            /mo
          </Mono>
        </View>
      </View>
      <Mono size={9} color={subtle} style={{ marginTop: 4, letterSpacing: 0.5 }}>
        {priceNote.toUpperCase()}
      </Mono>

      <View style={{ marginTop: 14 }}>
        {tier.features.map((row) => (
          <View
            key={row.label}
            style={{
              flexDirection: 'row',
              justifyContent: 'space-between',
              alignItems: 'center',
              paddingVertical: 7,
              borderTopWidth: 1,
              borderColor: rowBorder,
            }}
          >
            <Mono size={10} color={subtle} style={{ letterSpacing: 0.5 }}>
              {row.label.toUpperCase()}
            </Mono>
            <Mono size={11} color={row.emphasis ? palette.green[600] : ink} style={{ fontWeight: '700' }}>
              {row.value}
            </Mono>
          </View>
        ))}
      </View>

      <View style={{ marginTop: 14 }}>
        {isCurrent ? (
          <View style={{ backgroundColor: palette.ink, borderWidth: 2, borderColor: palette.ink, paddingVertical: 13, alignItems: 'center' }}>
            <Mono size={11} color={palette.bone} style={{ fontWeight: '700', letterSpacing: 1 }}>
              CURRENT PLAN ✓
            </Mono>
          </View>
        ) : tier.key === 'free' ? (
          <Button label="Downgrade to Free" onPress={onDowngrade} variant="secondary" />
        ) : (
          <Button label="Manage on Web →" onPress={onManageWeb} variant={isPro ? 'primary' : 'secondary'} />
        )}
      </View>
    </View>
  );
}
