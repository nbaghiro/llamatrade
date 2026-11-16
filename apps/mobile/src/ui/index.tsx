import { AlertTriangle, ChevronRight } from 'lucide-react-native';
import type { ReactNode } from 'react';
import { ActivityIndicator, Pressable, View, type StyleProp, type ViewStyle } from 'react-native';

import { makeStyles, radius, useTheme } from '../theme';
import { Text } from './Text';

export { Button } from './Button';
export { Field } from './Field';
export { Logo, LogoMark } from './Logo';
export { BackButton, Screen, ScreenHeader, type BackLink } from './Screen';
export { Segmented, type Segment } from './Segmented';
export { pnlTone, Text, type TextTone, type TextVariant } from './Text';

/* ---------------------------------------------------------------- Card ---- */

export function Card({
  children,
  style,
  onPress,
  onLongPress,
  selected = false,
}: {
  children: ReactNode;
  style?: StyleProp<ViewStyle>;
  onPress?: () => void;
  onLongPress?: () => void;
  /** Outlines the card in the accent, e.g. the current plan. */
  selected?: boolean;
}) {
  const s = useStyles();
  const body = [s.card, selected ? s.cardSelected : null, style];
  if (!onPress) return <View style={body}>{children}</View>;
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      onLongPress={onLongPress}
      style={({ pressed }) => [body, pressed ? s.pressed : null]}
    >
      {children}
    </Pressable>
  );
}

/* ------------------------------------------------------------- ListRow ---- */

/** One row of a grouped list inside a Card: label left, value or chevron right. */
export function ListRow({
  label,
  value,
  sub,
  right,
  onPress,
  last = false,
}: {
  label: ReactNode;
  value?: ReactNode;
  sub?: ReactNode;
  right?: ReactNode;
  onPress?: () => void;
  last?: boolean;
}) {
  const { c } = useTheme();
  const s = useStyles();
  const content = (
    <>
      <View style={s.rowMain}>
        {typeof label === 'string' ? <Text variant="body" numberOfLines={1}>{label}</Text> : label}
        {sub ? typeof sub === 'string' ? <Text variant="small" tone="fg3" numberOfLines={1}>{sub}</Text> : sub : null}
      </View>
      {value !== undefined ? typeof value === 'string' ? <Text variant="small" tone="fg3">{value}</Text> : value : null}
      {right}
      {onPress && !right ? <ChevronRight color={c.fg3} size={16} strokeWidth={1.8} /> : null}
    </>
  );
  const rowStyle = [s.row, last ? null : s.rowDivider];
  if (!onPress) return <View style={rowStyle}>{content}</View>;
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [rowStyle, pressed ? s.pressed : null]}>
      {content}
    </Pressable>
  );
}

/* ---------------------------------------------------------------- Pill ---- */

export type PillTone = 'neutral' | 'accent' | 'risk';

/** Small rounded tag in mono: neutral, accent for selection, risk for attention. */
export function Pill({ label, tone = 'neutral', dot = false }: { label: string; tone?: PillTone; dot?: boolean }) {
  const { c } = useTheme();
  const s = useStyles();
  const look = {
    neutral: { border: c.lineStrong, bg: 'transparent', fg: c.fg2, dot: c.fg3 },
    accent: { border: c.accentSoft, bg: c.accentSoft, fg: c.accent, dot: c.accent },
    risk: { border: c.riskLine, bg: c.riskSoft, fg: c.risk, dot: c.risk },
  }[tone];
  return (
    <View style={[s.pill, { borderColor: look.border, backgroundColor: look.bg }]}>
      {dot ? <View style={[s.pillDot, { backgroundColor: look.dot }]} /> : null}
      <Text variant="numSmall" color={look.fg} style={s.pillText}>
        {label}
      </Text>
    </View>
  );
}

/* ---------------------------------------------------------- StatusMark ---- */

export type RunState = 'running' | 'waiting' | 'paused' | 'frozen' | 'stopped' | 'error' | 'draft' | 'archived';

const RUN_LABEL: Record<RunState, string> = {
  running: 'Running',
  waiting: 'Waiting for data',
  paused: 'Paused',
  frozen: 'Frozen',
  stopped: 'Stopped',
  error: 'Error',
  draft: 'Draft',
  archived: 'Archived',
};

/** A dot and a word for a strategy or session state. Frozen and error are amber. */
export function StatusMark({ state, label }: { state: RunState; label?: string }) {
  const { c } = useTheme();
  const s = useStyles();
  const attention = state === 'frozen' || state === 'error';
  const dot: ViewStyle =
    state === 'running'
      ? { backgroundColor: c.fg, borderRadius: 4 }
      : state === 'waiting'
        ? { backgroundColor: c.fg3, borderRadius: 4 }
        : state === 'frozen'
          ? { backgroundColor: c.risk, borderRadius: 2 }
          : state === 'error'
            ? { borderWidth: 1.5, borderColor: c.risk, borderRadius: 1, transform: [{ rotate: '45deg' }, { scale: 0.86 }] }
            : state === 'draft' || state === 'archived'
              ? { borderWidth: 1.5, borderColor: c.fg3, borderRadius: 2 }
              : { borderWidth: 1.5, borderColor: c.fg3, borderRadius: 4 };
  return (
    <View style={s.status}>
      <View style={[s.statusDot, dot]} />
      <Text variant="small" tone={attention ? 'risk' : 'fg2'} style={s.statusText}>
        {label ?? RUN_LABEL[state]}
      </Text>
    </View>
  );
}

/* --------------------------------------------------------------- Meter ---- */

/** A rounded bar for a fraction 0..1, e.g. usage against a limit. */
export function Meter({ value, color, height = 5 }: { value: number; color?: string; height?: number }) {
  const { c } = useTheme();
  const v = Math.max(0, Math.min(1, Number.isFinite(value) ? value : 0));
  return (
    <View style={{ height, borderRadius: height, backgroundColor: c.sunk, overflow: 'hidden' }}>
      <View style={{ width: `${v * 100}%`, height: '100%', borderRadius: height, backgroundColor: color ?? c.accentFill }} />
    </View>
  );
}

/** Segments laid end to end by weight, e.g. holdings or sleeves. */
export function WeightStrip({ weights, height = 10 }: { weights: readonly number[]; height?: number }) {
  const { c } = useTheme();
  const s = useStyles();
  const shown = weights.filter((w) => w > 0);
  return (
    <View style={[s.strip, { height }]}>
      {shown.map((w, i) => (
        <View
          key={i}
          style={{ flex: w, borderRadius: 2, backgroundColor: c.chart[Math.min(i, c.chart.length - 1)] }}
        />
      ))}
    </View>
  );
}

/* -------------------------------------------------------------- Notice ---- */

/** One amber line that names a problem and what to do; neutral for quiet information. */
export function Notice({
  title,
  detail,
  tone = 'risk',
  action,
  onPress,
}: {
  title?: string;
  detail?: string;
  tone?: 'risk' | 'neutral';
  action?: ReactNode;
  onPress?: () => void;
}) {
  const { c } = useTheme();
  const s = useStyles();
  const risk = tone === 'risk';
  const box = [s.notice, risk ? { backgroundColor: c.riskSoft, borderColor: c.riskLine } : { backgroundColor: c.panel, borderColor: c.line }];
  const body = (
    <>
      {risk ? <AlertTriangle color={c.risk} size={16} strokeWidth={1.8} style={s.noticeIcon} /> : null}
      <View style={s.noticeText}>
        <Text variant="small">
          {title ? <Text variant="smallStrong" tone={risk ? 'risk' : 'fg'}>{title}</Text> : null}
          {title && detail ? ' ' : null}
          {detail ? <Text variant="small" tone="fg2">{detail}</Text> : null}
        </Text>
        {action}
      </View>
    </>
  );
  if (!onPress) return <View style={box}>{body}</View>;
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={box}>
      {body}
    </Pressable>
  );
}

/* --------------------------------------------------------- PanelError ---- */

/** Only the panel that failed changes: the cause and a retry. */
export function PanelError({ title, detail, onRetry }: { title: string; detail?: string; onRetry?: () => void }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <Card style={s.panelError}>
      <AlertTriangle color={c.risk} size={18} strokeWidth={1.8} />
      <Text variant="subhead" style={s.center}>{title}</Text>
      {detail ? <Text variant="small" tone="fg2" style={s.center}>{detail}</Text> : null}
      {onRetry ? (
        <Pressable accessibilityRole="button" onPress={onRetry} style={s.retry}>
          <Text variant="smallStrong">Try again</Text>
        </Pressable>
      ) : null}
    </Card>
  );
}

/* ------------------------------------------------------------- Loading ---- */

export function Loading({ label }: { label: string }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <View style={s.loading}>
      <ActivityIndicator color={c.fg3} />
      <Text variant="small" tone="fg3">{label}</Text>
    </View>
  );
}

export function EmptyState({ title, detail }: { title: string; detail?: string }) {
  const s = useStyles();
  return (
    <Card style={s.empty}>
      <Text variant="subhead" style={s.center}>{title}</Text>
      {detail ? <Text variant="small" tone="fg2" style={s.center}>{detail}</Text> : null}
    </Card>
  );
}

/** Small heading above a group, sentence case. */
export function SectionLabel({ children }: { children: ReactNode }) {
  return (
    <Text variant="label" tone="fg3" style={{ marginBottom: -4 }}>
      {children}
    </Text>
  );
}

const useStyles = makeStyles((t) => ({
  card: {
    backgroundColor: t.c.panel,
    borderWidth: 1,
    borderColor: t.c.line,
    borderRadius: radius.md,
    paddingHorizontal: 16,
    paddingVertical: 14,
  },
  cardSelected: { borderColor: t.c.accent },
  pressed: { opacity: 0.7 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 11 },
  rowDivider: { borderBottomWidth: 1, borderColor: t.c.line },
  rowMain: { flex: 1, gap: 2 },
  pill: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 5,
    height: 22,
    paddingHorizontal: 8,
    borderRadius: radius.pill,
    borderWidth: 1,
    alignSelf: 'flex-start',
  },
  pillDot: { width: 6, height: 6, borderRadius: 3 },
  pillText: { fontSize: 11, lineHeight: 14 },
  status: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  statusDot: { width: 7, height: 7 },
  statusText: { fontSize: 12.5, lineHeight: 16 },
  strip: { flexDirection: 'row', gap: 2 },
  notice: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 10,
    borderWidth: 1,
    borderRadius: radius.md,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  noticeIcon: { marginTop: 1 },
  noticeText: { flex: 1, gap: 8 },
  panelError: { alignItems: 'center', gap: 6, paddingVertical: 24 },
  center: { textAlign: 'center' },
  retry: {
    marginTop: 10,
    alignSelf: 'stretch',
    alignItems: 'center',
    paddingVertical: 10,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: t.c.lineStrong,
  },
  loading: { flex: 1, alignItems: 'center', justifyContent: 'center', gap: 10, paddingVertical: 60 },
  empty: { alignItems: 'center', gap: 6, paddingVertical: 28 },
}));
