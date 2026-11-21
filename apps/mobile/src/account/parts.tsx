/** Small pieces shared by the account, onboarding and sign-in screens. */
import { Check, X } from 'lucide-react-native';
import { Fragment, useState } from 'react';
import { Pressable, View, type LayoutChangeEvent } from 'react-native';
import Svg, { Line } from 'react-native-svg';

import { fonts, makeStyles, radius, useTheme } from '../theme';
import { Text } from '../ui';

/** The "A" tile that stands for Alpaca. */
export function AlpacaBadge({ size = 22, faded = false }: { size?: number; faded?: boolean }) {
  const s = useStyles();
  return (
    <View style={[s.alpaca, { width: size, height: size, borderRadius: Math.round(size * 0.27) }, faded ? s.faded : null]}>
      <Text variant="label" style={[s.alpacaText, { fontSize: Math.round(size * 0.5) }]}>
        A
      </Text>
    </View>
  );
}

export const PATH_STEPS = ['Backtest', 'Paper', 'Live'] as const;

/** Backtest, then paper, then live, with the steps up to `current` marked. */
export function StepLine({ current = 0 }: { current?: number }) {
  const s = useStyles();
  return (
    <View style={s.steps} accessibilityLabel={`Step ${current + 1} of 3: ${PATH_STEPS[current]}`}>
      {PATH_STEPS.map((step, i) => (
        <Fragment key={step}>
          {i > 0 ? <View style={[s.stepLine, i <= current ? s.stepLineOn : null]} /> : null}
          <View style={s.step}>
            <View style={[s.stepDot, i <= current ? s.stepDotOn : null]} />
            <Text variant="label" tone={i <= current ? 'fg' : 'fg3'}>
              {step}
            </Text>
          </View>
        </Fragment>
      ))}
    </View>
  );
}

/** One line of what LlamaTrade can or can't do with a connection. */
export function CheckLine({ ok, label, detail }: { ok: boolean; label: string; detail?: string }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <View style={s.check}>
      <View style={[s.checkBox, ok ? s.checkOk : s.checkNo]}>
        {ok ? <Check color={c.accent} size={11} strokeWidth={2.6} /> : <X color={c.fg3} size={11} strokeWidth={2.6} />}
      </View>
      <Text variant="small" tone={ok ? 'fg' : 'fg2'} style={s.flex}>
        {label}
      </Text>
      {detail ? <Text variant="numSmall" tone="fg3">{detail}</Text> : null}
    </View>
  );
}

/** A short state on the right of a row: plain, or amber when it needs attention. */
export function StateText({ label, risk = false }: { label: string; risk?: boolean }) {
  return (
    <Text variant="small" tone={risk ? 'risk' : 'fg3'} numberOfLines={1}>
      {label}
    </Text>
  );
}

/** A usage bar with a dashed stretch to where the month is heading. */
export function ForecastMeter({ fraction, forecast, risk = false }: { fraction: number; forecast: number | null; risk?: boolean }) {
  const { c } = useTheme();
  const s = useStyles();
  const [w, setW] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setW(Math.round(e.nativeEvent.layout.width));
  const used = Math.max(0, Math.min(1, fraction));
  const ahead = forecast !== null ? Math.max(used, Math.min(1, forecast)) : used;
  const fill = risk ? c.risk : c.accent;
  return (
    <View style={s.meter} onLayout={onLayout}>
      {w > 0 ? (
        <Svg width={w} height={6}>
          <Line x1={3} x2={w - 3} y1={3} y2={3} stroke={c.sunk} strokeWidth={6} strokeLinecap="round" />
          {ahead > used ? (
            <Line x1={Math.max(3, used * w)} x2={Math.max(3, ahead * w - 3)} y1={3} y2={3} stroke={fill} strokeOpacity={0.7} strokeWidth={2} strokeDasharray="3 3" />
          ) : null}
          {used > 0 ? <Line x1={3} x2={Math.max(3, used * w - 3)} y1={3} y2={3} stroke={fill} strokeWidth={6} strokeLinecap="round" /> : null}
        </Svg>
      ) : null}
    </View>
  );
}

/** A tappable text link in the accent. */
export function TextLink({ label, onPress, align = 'left' }: { label: string; onPress: () => void; align?: 'left' | 'right' | 'center' }) {
  const s = useStyles();
  return (
    <Pressable accessibilityRole="link" onPress={onPress} hitSlop={8} style={align === 'right' ? s.right : align === 'center' ? s.center : null}>
      <Text variant="small" tone="accent">
        {label}
      </Text>
    </Pressable>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  alpaca: { alignItems: 'center', justifyContent: 'center', backgroundColor: t.c.fg },
  alpacaText: { color: t.c.canvas, fontFamily: fonts.bold, lineHeight: undefined },
  faded: { opacity: 0.45 },
  steps: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  step: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  stepDot: { width: 8, height: 8, borderRadius: 4, borderWidth: 1.5, borderColor: t.c.fg3 },
  stepDotOn: { backgroundColor: t.c.accent, borderColor: t.c.accent },
  stepLine: { flex: 1, height: 1, backgroundColor: t.c.lineStrong },
  stepLineOn: { backgroundColor: t.c.accent },
  check: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  checkBox: { width: 18, height: 18, borderRadius: radius.xs, alignItems: 'center', justifyContent: 'center', borderWidth: 1 },
  checkOk: { borderColor: t.c.accent, backgroundColor: t.c.accentSoft },
  checkNo: { borderColor: t.c.lineStrong },
  meter: { height: 6, justifyContent: 'center' },
  right: { alignSelf: 'flex-end' },
  center: { alignSelf: 'center' },
}));
