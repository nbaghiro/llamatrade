import {
  BillingInterval,
  InvoiceStatus,
  PlanTier,
  SubscriptionStatus,
  type Invoice,
  type PaymentMethod,
  type Subscription,
} from '@llamatrade/core/proto/billing_pb';
import type { Money, Timestamp } from '@llamatrade/core/proto/common_pb';
import { router } from 'expo-router';
import { CreditCard, Zap } from 'lucide-react-native';
import { useEffect } from 'react';
import { ActivityIndicator, Pressable, RefreshControl, ScrollView, View, type ViewStyle } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useBillingStore } from '../../src/stores/billing';
import { useAuthStore } from '../../src/stores/auth';
import { fonts, palette } from '../../src/theme';
import { Badge, Body, Card, Display, Label, Mono } from '../../src/ui';

/* --------------------------------------------------------------- helpers ---- */
function hardShadow(color: string): ViewStyle {
  return { shadowColor: color, shadowOffset: { width: 5, height: 5 }, shadowOpacity: 1, shadowRadius: 0, elevation: 6 };
}

function moneyNum(m?: Money): number {
  return m?.amount ? parseFloat(m.amount) || 0 : 0;
}

function tsDate(ts?: Timestamp): Date | null {
  return ts?.seconds ? new Date(Number(ts.seconds) * 1000) : null;
}

function fmtDay(ts?: Timestamp): string {
  const d = tsDate(ts);
  return d ? d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' }) : '—';
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
  return (sub?.plan?.name || TIER_LABEL[sub?.plan?.tier ?? PlanTier.FREE] || 'Free').toUpperCase();
}

function subStatus(sub: Subscription | null): { label: string; variant: 'green' | 'orange' | 'red' | 'ink' | 'gray' | 'blue' } {
  if (!sub) return { label: 'No plan', variant: 'gray' };
  if (sub.cancelAtPeriodEnd) return { label: 'Canceling', variant: 'orange' };
  switch (sub.status) {
    case SubscriptionStatus.ACTIVE:
      return { label: 'Active', variant: 'green' };
    case SubscriptionStatus.TRIALING:
      return { label: 'Trial', variant: 'blue' };
    case SubscriptionStatus.PAST_DUE:
      return { label: 'Past due', variant: 'red' };
    case SubscriptionStatus.PAUSED:
      return { label: 'Paused', variant: 'ink' };
    case SubscriptionStatus.CANCELED:
      return { label: 'Canceled', variant: 'gray' };
    default:
      return { label: '—', variant: 'gray' };
  }
}

function renewalLine(sub: Subscription | null): string {
  if (!sub) return '';
  if (sub.status === SubscriptionStatus.TRIALING && sub.trialEnd) return `Trial ends ${fmtDay(sub.trialEnd)}`;
  if (sub.cancelAtPeriodEnd) return `Ends ${fmtDay(sub.currentPeriodEnd)}`;
  return `Renews ${fmtDay(sub.currentPeriodEnd)}`;
}

/* ----------------------------------------------------------------- meters --- */
function MeterRow({ label, used, limit }: { label: string; used: number; limit: number }) {
  const unlimited = limit <= 0;
  const ratio = unlimited ? (used > 0 ? 0.12 : 0.06) : Math.min(1, used / limit);
  const atLimit = !unlimited && used >= limit;
  const barColor = unlimited
    ? palette.green[500]
    : atLimit
      ? palette.red[500]
      : ratio >= 0.8
        ? palette.orange[500]
        : palette.green[500];
  const note = unlimited ? 'Unlimited' : atLimit ? 'At limit · upgrade' : `${(limit - used).toLocaleString('en-US')} left`;

  return (
    <View>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'baseline' }}>
        <Label color={palette.ink}>{label}</Label>
        <Mono size={11} style={{ fontWeight: '700' }}>
          {used.toLocaleString('en-US')}
          <Mono size={11} color={palette.gray[400]}> / {unlimited ? '∞' : limit.toLocaleString('en-US')}</Mono>
        </Mono>
      </View>
      <View style={{ height: 7, borderWidth: 1.5, borderColor: palette.ink, backgroundColor: palette.bone, marginTop: 4 }}>
        <View style={{ height: '100%', width: `${Math.max(4, ratio * 100)}%`, backgroundColor: barColor }} />
      </View>
      <Mono size={8} color={atLimit ? palette.red[600] : palette.gray[500]} style={{ marginTop: 3, letterSpacing: 0.5 }}>
        {note.toUpperCase()}
      </Mono>
    </View>
  );
}

/* ------------------------------------------------------------ payment card -- */
function PaymentCard({ pm, holder }: { pm?: PaymentMethod; holder: string }) {
  const brand = (pm?.cardBrand || 'card').toUpperCase();
  const last4 = pm?.cardLast4 || '••••';
  const exp = pm ? `${String(pm.cardExpMonth).padStart(2, '0')} / ${String(pm.cardExpYear % 100).padStart(2, '0')}` : '—';
  const dim = 'rgba(251,248,241,0.66)';

  return (
    <View style={[{ backgroundColor: palette.ink, borderWidth: 2, borderColor: palette.ink }, hardShadow(palette.orange[500])]}>
      <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: 16, paddingTop: 15 }}>
        <Body size={19} color={palette.bone} style={{ fontFamily: fonts.display, textTransform: 'uppercase', letterSpacing: 1 }}>
          {brand}
        </Body>
        {pm?.isDefault ? <Badge label="Default" variant="orange" /> : <CreditCard color={dim} size={16} strokeWidth={2} />}
      </View>
      <View style={{ paddingHorizontal: 16, paddingTop: 18, paddingBottom: 4 }}>
        <Mono size={15} color={palette.bone} style={{ letterSpacing: 2 }}>
          ••••  ••••  ••••  {last4}
        </Mono>
      </View>
      <View
        style={{
          flexDirection: 'row',
          justifyContent: 'space-between',
          alignItems: 'flex-end',
          borderTopWidth: 1,
          borderColor: 'rgba(251,248,241,0.15)',
          paddingHorizontal: 16,
          paddingVertical: 11,
          marginTop: 8,
        }}
      >
        <Mono size={10} color={palette.bone} style={{ letterSpacing: 1 }}>
          {(holder || '—').toUpperCase()}
        </Mono>
        <Mono size={9} color={dim}>
          EXP <Mono size={9} color={palette.bone} style={{ fontWeight: '700' }}>{exp}</Mono>
        </Mono>
      </View>
    </View>
  );
}

/* ---------------------------------------------------------------- invoices -- */
function InvoiceRow({ inv, first }: { inv: Invoice; first: boolean }) {
  const paid = inv.status === InvoiceStatus.PAID;
  const amt = moneyNum(inv.amountPaid ?? inv.amount);
  const desc = inv.items[0]?.description || 'Subscription';
  return (
    <View
      style={{
        flexDirection: 'row',
        alignItems: 'center',
        gap: 10,
        paddingVertical: 9,
        borderTopWidth: first ? 0 : 1.5,
        borderColor: palette.bone2,
      }}
    >
      <View style={{ flex: 1 }}>
        <Mono size={11} style={{ fontWeight: '700' }} numberOfLines={1}>
          {desc}
        </Mono>
        <Label style={{ marginTop: 2 }}>{fmtDay(inv.paidAt ?? inv.periodStart)}</Label>
      </View>
      <Display size={14}>{fmtUsd(amt)}</Display>
      <Badge label={paid ? 'Paid' : 'Due'} variant={paid ? 'green' : 'orange'} />
    </View>
  );
}

/* ----------------------------------------------------------------- screen --- */
export default function AccountScreen() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const { subscription, usage, paymentMethods, invoices, loading, refreshing, loaded, error, fetch } = useBillingStore();

  useEffect(() => {
    void fetch();
  }, [fetch]);

  const name = user ? `${user.firstName ?? ''} ${user.lastName ?? ''}`.trim() || user.email : '—';
  const initial = (user?.firstName ?? user?.email ?? '?').charAt(0).toUpperCase();
  const status = subStatus(subscription);
  const price = moneyNum(subscription?.currentPrice) || moneyNum(subscription?.plan?.monthlyPrice);
  const per = subscription?.interval === BillingInterval.YEARLY ? 'yr' : 'mo';
  const plan = subscription?.plan;
  const defaultPm = paymentMethods.find((p) => p.isDefault) ?? paymentMethods[0];

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: palette.bone }}>
      <View
        style={{
          height: 46,
          borderBottomWidth: 2,
          borderColor: palette.ink,
          backgroundColor: palette.paper,
          flexDirection: 'row',
          alignItems: 'center',
          paddingHorizontal: 14,
        }}
      >
        <Display size={16}>Account</Display>
      </View>

      <ScrollView
        contentContainerStyle={{ padding: 12, gap: 11 }}
        showsVerticalScrollIndicator={false}
        refreshControl={<RefreshControl refreshing={refreshing} onRefresh={() => void fetch({ refresh: true })} tintColor={palette.ink} />}
      >
        {/* Profile */}
        <Card shadow style={{ flexDirection: 'row', alignItems: 'center', gap: 11 }}>
          <View style={{ width: 44, height: 44, backgroundColor: palette.orange[500], borderWidth: 2, borderColor: palette.ink, alignItems: 'center', justifyContent: 'center' }}>
            <Display size={20}>{initial}</Display>
          </View>
          <View style={{ flex: 1 }}>
            <Body size={14} style={{ fontWeight: '700' }} numberOfLines={1}>
              {name}
            </Body>
            <Label style={{ marginTop: 2 }} numberOfLines={1}>
              {user?.email ?? '—'} · #{(user?.tenantId ?? '').slice(0, 4).toUpperCase()}
            </Label>
          </View>
          <Badge label={tierName(subscription)} variant="orange" />
        </Card>

        {loading && !loaded ? (
          <View style={{ paddingVertical: 40, alignItems: 'center', gap: 10 }}>
            <ActivityIndicator color={palette.ink} />
            <Label>Loading billing…</Label>
          </View>
        ) : (
          <>
            {error ? (
              <Card style={{ backgroundColor: palette.red[50], borderColor: palette.red[500] }}>
                <Mono size={10} color={palette.red[600]}>{error}</Mono>
              </Card>
            ) : null}

            {/* Plan */}
            <Card shadow>
              <View style={{ flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' }}>
                <Label>Current Plan</Label>
                <Badge label={status.label} variant={status.variant} />
              </View>
              <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 8, marginTop: 6 }}>
                <Display size={26}>{tierName(subscription)}</Display>
                {price > 0 ? (
                  <Mono size={12} color={palette.gray[600]} style={{ fontWeight: '700' }}>
                    ${Math.round(price)} / {per}
                  </Mono>
                ) : null}
              </View>
              <Label style={{ marginTop: 3 }}>{renewalLine(subscription)}</Label>

              {usage && plan ? (
                <View style={{ gap: 11, marginTop: 14 }}>
                  <MeterRow label="Strategies" used={usage.strategiesCreated} limit={plan.maxStrategies} />
                  <MeterRow label="Backtests" used={usage.backtestsRun} limit={plan.maxBacktestsPerMonth} />
                  <MeterRow label="Live Sessions" used={usage.liveSessions} limit={plan.maxLiveSessions} />
                  <MeterRow label="Copilot Msgs" used={Number(usage.apiCalls)} limit={-1} />
                </View>
              ) : null}
            </Card>

            {/* Payment method */}
            <View style={{ gap: 7, marginTop: 2 }}>
              <Label style={{ marginLeft: 2 }}>Payment Method</Label>
              <PaymentCard pm={defaultPm} holder={name} />
            </View>

            {/* Billing history */}
            {invoices.length ? (
              <Card>
                <Label>Billing History</Label>
                <View style={{ marginTop: 6 }}>
                  {invoices.slice(0, 3).map((inv, i) => (
                    <InvoiceRow key={inv.id} inv={inv} first={i === 0} />
                  ))}
                </View>
                {invoices.length > 3 ? (
                  <Mono size={9} color={palette.gray[500]} style={{ marginTop: 8 }}>
                    + {invoices.length - 3} MORE · VIEW ALL ON DESKTOP
                  </Mono>
                ) : null}
              </Card>
            ) : null}
          </>
        )}

        {/* Broker connect — not yet built on mobile */}
        <Card style={{ backgroundColor: palette.bone2 }}>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
            <Zap color={palette.gray[500]} size={14} strokeWidth={2.5} />
            <Badge label="Coming soon" variant="gray" />
          </View>
          <Body size={13} style={{ fontWeight: '700', marginTop: 8 }}>Connect your broker to trade live</Body>
          <Label style={{ marginTop: 4 }}>Bring your own Alpaca keys (stored in the device Keychain) — landing soon on mobile.</Label>
          <View style={{ marginTop: 10, alignSelf: 'flex-start', flexDirection: 'row', alignItems: 'center', gap: 6, backgroundColor: palette.gray[200], borderWidth: 2, borderColor: palette.gray[400], paddingHorizontal: 14, paddingVertical: 8 }}>
            <Mono size={9} color={palette.gray[600]} style={{ fontWeight: '700' }}>CONNECT ALPACA</Mono>
            <Mono size={8} color={palette.gray[500]}>· SOON</Mono>
          </View>
        </Card>

        {/* Dev-only streaming spike (not shipped in release builds) */}
        {__DEV__ ? (
          <Pressable
            onPress={() => router.push('/spike')}
            style={{ backgroundColor: palette.ink, borderWidth: 2, borderColor: palette.ink, paddingVertical: 11, alignItems: 'center', marginTop: 2 }}
          >
            <Mono size={10} color={palette.orange[500]} style={{ fontWeight: '700' }}>▶  DEV · STREAMING SPIKE</Mono>
          </Pressable>
        ) : null}

        <Pressable
          onPress={logout}
          style={{ backgroundColor: palette.paper, borderWidth: 2, borderColor: palette.red[500], paddingVertical: 12, alignItems: 'center' }}
        >
          <Mono size={11} color={palette.red[600]} style={{ fontWeight: '700' }}>LOG OUT</Mono>
        </Pressable>
      </ScrollView>
    </SafeAreaView>
  );
}
