/** Shared chrome for the sign-in, create-account and reset screens (account/sign-in2 A). */
import { ConnectError } from '@connectrpc/connect';
import type { ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { LineChart } from '../charts/LineChart';
import { makeStyles, space } from '../theme';
import { BackButton, BrandLockup, Canvas, Notice, Text, type BackLink } from '../ui';
import type { AuthFailure } from './errors';
import { exampleBacktest } from './example';

/** A thrown auth error as plain data for `errors.ts`. */
export function toFailure(e: unknown): AuthFailure {
  if (e instanceof ConnectError) return { code: e.code, message: e.rawMessage || e.message };
  if (e instanceof TypeError) return { code: null, message: e.message, network: true };
  return { code: null, message: e instanceof Error ? e.message : '' };
}

const pct = (v: number) => `${v >= 0 ? '+' : '−'}${Math.abs(v * 100).toFixed(1)}%`;

/** Every fifth point is plenty for a strip this small. */
function thin(values: readonly number[]): number[] {
  return values.filter((_, i) => i % 5 === 0 || i === values.length - 1);
}

/** The illustrative Recession Radar example as a strip above the form. */
export function ExampleStrip({ caption = true, height = 64 }: { caption?: boolean; height?: number }) {
  const s = useStyles();
  const ex = exampleBacktest();
  return (
    <View style={s.strip}>
      <View style={s.stripHead}>
        <Text variant="label" tone="fg2" style={s.flex} numberOfLines={1}>
          Example backtest · {ex.name}
        </Text>
        <Text variant="numSmall" tone="gain">
          {pct(ex.total)}
        </Text>
      </View>
      <LineChart values={thin(ex.strategy)} benchmark={thin(ex.benchmarkValues)} height={height} />
      {caption ? (
        <Text variant="caption" tone="fg3">
          {ex.benchmark} {pct(ex.benchmarkTotal)} over the same two years. Illustrative figures, not anyone&apos;s account.
        </Text>
      ) : null}
    </View>
  );
}

export function AuthShell({
  title,
  subtitle,
  back,
  artSeed,
  top,
  footer = true,
  children,
}: {
  title: string;
  subtitle: string;
  back?: BackLink;
  artSeed: string;
  /** Sits between the brand and the title: the example strip or the step line. */
  top?: ReactNode;
  footer?: boolean;
  children: ReactNode;
}) {
  const s = useStyles();
  return (
    <Canvas art="bold" artSeed={artSeed}>
      <SafeAreaView style={s.flex}>
        <KeyboardAvoidingView style={s.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled" showsVerticalScrollIndicator={false}>
            {back ? <BackButton back={back} /> : <View style={s.brand}><BrandLockup size={34} /></View>}
            {top}
            <View style={s.heading}>
              <Text variant="title">{title}</Text>
              <Text variant="body" tone="fg2">{subtitle}</Text>
            </View>
            {children}
            {footer ? (
              <>
                <View style={s.grow} />
                <Text variant="caption" tone="fg3" style={s.foot}>
                  Closed beta · invite only · paper and live trading on Alpaca
                </Text>
              </>
            ) : null}
          </ScrollView>
        </KeyboardAvoidingView>
      </SafeAreaView>
    </Canvas>
  );
}

export function FormError({ message }: { message: string | null }) {
  return message ? <Notice detail={message} /> : null;
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  grow: { flexGrow: 1 },
  body: { flexGrow: 1, paddingHorizontal: space.gutter, paddingTop: 12, paddingBottom: 20, gap: 14 },
  brand: { marginBottom: 4 },
  heading: { gap: 4, marginTop: 4, marginBottom: 2 },
  strip: {
    gap: 8,
    padding: 12,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: t.c.line,
    backgroundColor: t.c.panel,
  },
  stripHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  foot: { textAlign: 'center', marginTop: 8 },
}));
