/** Home's blocks: section heads, session rows by account, the split, the timeline and the attention tray. */

import { money, pct, qty, signedMoney } from '@llamatrade/core/format';
import { router } from 'expo-router';
import { ChevronRight, Clock, Search } from 'lucide-react-native';
import { useState, type ReactNode } from 'react';
import { Pressable, View } from 'react-native';

import { SplitBar } from '../charts/SplitBar';
import { Sparkline } from '../charts/Sparkline';
import { HeaderActions } from '../shell/HeaderActions';
import { makeStyles, radius, useTheme } from '../theme';
import { Card, LogoMark, Text, pnlTone } from '../ui';
import { isQuiet, type AccountSplit, type Attention, type Mode, type SessionRow, type TimelineEntry } from './model';
import { PaperAmount } from './PaperAmount';
import { dayLabel, hm, shortDate } from './when';

/* ----------------------------------------------------------- top row ---- */

/** Logo on the left; search, bell and avatar on the right. */
export function HomeTopRow() {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <View style={s.topRow}>
      <LogoMark size={26} bold />
      <View style={s.topRight}>
        <SearchButton color={c.fg2} />
        <HeaderActions />
      </View>
    </View>
  );
}

export function SearchButton({ color }: { color: string }) {
  const s = useStyles();
  return (
    <Pressable accessibilityRole="button" accessibilityLabel="Search" onPress={() => router.push('/search')} hitSlop={8} style={s.icon}>
      <Search color={color} size={20} strokeWidth={1.7} />
    </Pressable>
  );
}

/* ------------------------------------------------------- section head ---- */

export function SectionHead({ title, link, onPress }: { title: string; link?: string; onPress?: () => void }) {
  const s = useStyles();
  return (
    <View style={s.sectionHead}>
      <Text variant="subhead">{title}</Text>
      {link && onPress ? (
        <Text variant="small" tone="accent" onPress={onPress}>
          {link}
        </Text>
      ) : null}
    </View>
  );
}

/* ------------------------------------------------------------ the split -- */

export type ChartFilter = 'both' | 'live' | 'paper';

/** Live solid and paper hatched, with both figures; tapping a side filters the chart (hero B). */
export function SplitBlock({
  split,
  filter,
  onFilter,
}: {
  split: AccountSplit;
  filter: ChartFilter;
  onFilter: (f: ChartFilter) => void;
}) {
  const s = useStyles();
  const share = (v: number) => (split.total > 0 ? `${((v / split.total) * 100).toFixed(1)}%` : '');
  const toggle = (f: ChartFilter) => onFilter(filter === f ? 'both' : f);
  return (
    <Card style={s.split}>
      <SplitBar
        segments={[
          { key: 'live', value: split.live, look: 'solid', label: 'Live' },
          { key: 'paper', value: split.paper, look: 'hatched', label: 'Paper' },
        ]}
        selected={filter === 'both' ? null : filter}
        onPress={(k) => toggle(k === 'live' ? 'live' : 'paper')}
      />
      {(['live', 'paper'] as const).map((m) => {
        const v = m === 'live' ? split.live : split.paper;
        const dim = filter !== 'both' && filter !== m;
        return (
          <Pressable
            key={m}
            accessibilityRole="button"
            accessibilityState={{ selected: filter === m }}
            onPress={() => toggle(m)}
            style={[s.splitRow, dim ? s.dim : null]}
          >
            <ModeSwatch mode={m} />
            <Text variant="body" style={s.flex}>
              {m === 'live' ? 'Live' : 'Paper'}
            </Text>
            <PaperAmount paper={m === 'paper'} variant="numStrong">
              {money(v, 2)}
            </PaperAmount>
            <Text variant="numSmall" tone="fg3" style={s.share}>
              {share(v)}
            </Text>
          </Pressable>
        );
      })}
      {!split.liveKnown ? (
        <Text variant="caption" tone="fg3">
          Live cash couldn't be read, so the live figure counts sessions only.
        </Text>
      ) : null}
    </Card>
  );
}

/** A square for live (ink) or a hatched square for paper. */
export function ModeSwatch({ mode }: { mode: Mode }) {
  const s = useStyles();
  return <View style={[s.swatch, mode === 'paper' ? s.swatchPaper : null]} />;
}

/* --------------------------------------------------------- session rows -- */

function stateLine(r: SessionRow, next: string | null): string {
  const mode = r.mode === 'live' ? 'Live' : 'Paper';
  switch (r.state) {
    case 'frozen':
      return `${mode} · frozen`;
    case 'error':
      return `${mode} · error`;
    case 'paused':
      return `${mode} · paused`;
    case 'waiting':
      return `${mode} · waiting for data`;
    case 'stopped':
      return `${mode} · stopped${r.endedAt ? ` ${shortDate(r.endedAt)}` : ''}`;
    default:
      return next ? `${mode} · rebalances ${next}` : `${mode} · running`;
  }
}

/** One session: name, state and next rebalance, sparkline, value and today's move. */
export function SessionRowView({
  row,
  next,
  last,
  onPress,
}: {
  row: SessionRow;
  next: string | null;
  last: boolean;
  onPress: () => void;
}) {
  const s = useStyles();
  const stopped = row.state === 'stopped';
  const attention = row.state === 'frozen' || row.state === 'error';
  return (
    <Pressable
      accessibilityRole="button"
      onPress={onPress}
      style={({ pressed }) => [s.row, last ? null : s.rowDivider, pressed ? s.pressed : null]}
    >
      <View style={s.rowMain}>
        <Text variant="bodyStrong" tone={stopped ? 'fg2' : 'fg'} numberOfLines={1}>
          {row.title}
        </Text>
        <Text variant="small" tone={attention ? 'risk' : 'fg3'} numberOfLines={1}>
          {stateLine(row, next)}
        </Text>
      </View>
      <Sparkline values={row.spark} width={60} height={22} muted={stopped} />
      <View style={s.figures}>
        {row.value !== null ? (
          <PaperAmount paper={row.mode === 'paper'} variant="numStrong" tone={stopped ? 'fg2' : 'fg'}>
            {money(row.value, 2)}
          </PaperAmount>
        ) : (
          <Text variant="numSmall" tone="fg3">
            No value yet
          </Text>
        )}
        {row.today !== null ? (
          <Text variant="numSmall" tone={isQuiet(row.dayReturnPct) ? 'fg2' : pnlTone(row.today)}>
            {pct(row.dayReturnPct)}
          </Text>
        ) : (
          <Text variant="numSmall" tone="fg3">
            {stopped ? 'In cash' : ' '}
          </Text>
        )}
      </View>
    </Pressable>
  );
}

/**
 * Sessions in two lanes, live above paper, each account's card headed by its total (sessions
 * D in the list-first layout). Each row is the list-first row with its sparkline.
 */
export function SessionsByAccount({
  rows,
  split,
  nextFor,
  onOpen,
}: {
  rows: readonly SessionRow[];
  split: AccountSplit;
  nextFor: (row: SessionRow) => string | null;
  onOpen: (row: SessionRow) => void;
}) {
  const s = useStyles();
  const groups = (['live', 'paper'] as const)
    .map((m) => ({ mode: m, rows: rows.filter((r) => r.mode === m) }))
    .filter((g) => g.rows.length > 0);
  return (
    <View style={s.groups}>
      {groups.map((g) => (
        <Card key={g.mode} style={[s.group, g.mode === 'paper' ? s.groupPaper : null]}>
          <View style={s.groupHead}>
            <View style={[s.modeTag, g.mode === 'live' ? s.modeTagLive : null]}>
              <Text variant="numSmall" style={[s.modeTagText, g.mode === 'live' ? s.modeTagTextLive : null]}>
                {g.mode === 'live' ? 'LIVE' : 'PAPER'}
              </Text>
            </View>
            <Text variant="caption" tone="fg3" style={s.flex}>
              {g.mode === 'live' ? 'Real money' : 'Simulated'}
            </Text>
            <PaperAmount paper={g.mode === 'paper'} variant="numStrong">
              {money(g.mode === 'live' ? split.live : split.paper, 2)}
            </PaperAmount>
          </View>
          {g.rows.map((r, i) => (
            <SessionRowView key={r.id} row={r} next={nextFor(r)} last={i === g.rows.length - 1} onPress={() => onOpen(r)} />
          ))}
        </Card>
      ))}
    </View>
  );
}

/* ------------------------------------------------------------ timeline -- */

/** Today's fills, a Now row and the next two weeks' planned rebalances (activity B). */
export function TimelineCard({
  entries,
  now,
  onOpenSession,
}: {
  entries: readonly TimelineEntry[];
  now: number;
  onOpenSession: (sessionId: string) => void;
}) {
  const s = useStyles();
  const fills = entries.filter((e) => e.kind === 'fill').length;
  const planned = entries.filter((e) => e.kind === 'planned').length;
  return (
    <Card style={s.timeline}>
      {fills === 0 ? (
        <View style={s.tlRow}>
          <Text variant="numSmall" tone="fg3" style={s.tlWhen}>
            Today
          </Text>
          <Text variant="small" tone="fg3" style={s.flex}>
            No fills yet today.
          </Text>
        </View>
      ) : null}
      {entries.map((e) => {
        if (e.kind === 'now') {
          return (
            <View key="now" style={s.nowRow}>
              <Text variant="numSmall" style={s.nowLabel}>
                Now {hm(now)}
              </Text>
              <View style={s.nowLine} />
            </View>
          );
        }
        if (e.kind === 'fill') {
          const f = e.fill;
          return (
            <View key={e.key} style={s.tlRow}>
              <Text variant="numSmall" tone="fg3" style={s.tlWhen}>
                {hm(f.t)}
              </Text>
              <View style={s.flex}>
                <Text variant="small">
                  <Text variant="smallStrong">{f.symbol}</Text> {f.side === 'buy' ? 'bought' : 'sold'} {qty(f.qty)}
                </Text>
                <Text variant="caption" tone="fg3">
                  {[e.session, e.mode, f.price > 0 ? money(f.qty * f.price, 2) : ''].filter(Boolean).join(' · ')}
                </Text>
              </View>
            </View>
          );
        }
        const p = e.planned;
        return (
          <Pressable key={e.key} onPress={() => onOpenSession(p.sessionId)} style={({ pressed }) => [s.tlRow, pressed ? s.pressed : null]}>
            <Text variant="numSmall" tone="fg3" style={s.tlWhen}>
              {dayLabel(p.day, now)}
            </Text>
            <View style={s.flex}>
              <Text variant="small">{p.name} rebalances</Text>
              <Text variant="caption" tone="fg3">
                Planned · {p.cadence} · {p.mode}
              </Text>
            </View>
          </Pressable>
        );
      })}
      {planned === 0 ? (
        <Text variant="caption" tone="fg3" style={s.tlFoot}>
          Nothing is planned in the next two weeks.
        </Text>
      ) : (
        <Text variant="caption" tone="fg3" style={s.tlFoot}>
          Planned dates follow each strategy's schedule. A market holiday can move one by a day.
        </Text>
      )}
    </Card>
  );
}

/* ----------------------------------------------------------- attention -- */

/**
 * Stacked amber cards over the top of the chart, newest in front, with the count; swiping or
 * tapping Next brings the next one forward (attention2 C).
 */
export function AttentionTray({ items, onReview }: { items: readonly Attention[]; onReview: (a: Attention) => void }) {
  const { c } = useTheme();
  const s = useStyles();
  const [index, setIndex] = useState(0);
  if (items.length === 0) return null;
  const i = Math.min(index, items.length - 1);
  const item = items[i];
  const next = () => setIndex((i + 1) % items.length);
  return (
    <View style={s.tray}>
      {items.length > 1 ? <View style={[s.trayBehind, s.trayBehind2]} /> : null}
      {items.length > 1 ? <View style={s.trayBehind} /> : null}
      <Pressable
        accessibilityRole="button"
        accessibilityHint="Opens what needs you"
        onPress={() => onReview(item)}
        onLongPress={items.length > 1 ? next : undefined}
        style={s.trayCard}
      >
        <View style={s.trayHead}>
          <View style={s.trayDot} />
          <Text variant="smallStrong" style={s.flex}>
            {item.title}
          </Text>
          <ChevronRight color={c.risk} size={16} strokeWidth={1.8} />
        </View>
        <Text variant="small" tone="fg2">
          {item.detail}
        </Text>
        {items.length > 1 ? (
          <View style={s.trayFoot}>
            <Text variant="caption" tone="fg3" style={s.flex}>
              {i + 1} of {items.length}
            </Text>
            <Text variant="caption" tone="accent" onPress={next}>
              Next
            </Text>
          </View>
        ) : null}
      </Pressable>
    </View>
  );
}

/* --------------------------------------------------------------- misc ---- */

export function NextOpenLine({ children }: { children: ReactNode }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <View style={s.nextOpen}>
      <Clock color={c.fg3} size={13} strokeWidth={1.8} />
      <Text variant="small" tone="fg3">
        {children}
      </Text>
    </View>
  );
}

/** The day's change, toned only when it's a real move. */
export function DayChange({ amount, percent, suffix }: { amount: number; percent: number; suffix?: string }) {
  const s = useStyles();
  const tone = isQuiet(percent) ? 'fg2' : pnlTone(amount);
  return (
    <View style={s.dayChange}>
      <Text variant="numStrong" tone={tone}>
        {signedMoney(amount, 2)} ({pct(percent)})
      </Text>
      {suffix ? (
        <Text variant="small" tone="fg3">
          {suffix}
        </Text>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  dim: { opacity: 0.45 },
  pressed: { opacity: 0.7 },
  topRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', minHeight: 36 },
  topRight: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  icon: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center' },
  sectionHead: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between', marginTop: 8, marginBottom: -4 },
  split: { gap: 10, paddingVertical: 12 },
  splitRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  share: { width: 48, textAlign: 'right' },
  swatch: { width: 10, height: 10, borderRadius: 2, backgroundColor: t.c.fg },
  swatchPaper: { backgroundColor: 'transparent', borderWidth: 1.5, borderColor: t.c.accent, borderStyle: 'dashed' },
  groups: { gap: 10 },
  group: { paddingVertical: 4 },
  groupPaper: { borderStyle: 'dashed', borderColor: t.c.lineStrong },
  groupHead: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingTop: 10, paddingBottom: 6 },
  modeTag: { borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.pill, paddingHorizontal: 7, paddingVertical: 1 },
  modeTagLive: { backgroundColor: t.c.fg, borderColor: t.c.fg },
  modeTagText: { fontSize: 10, lineHeight: 14, color: t.c.fg2, letterSpacing: 0.4 },
  modeTagTextLive: { color: t.c.canvas },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 11 },
  rowDivider: { borderBottomWidth: 1, borderColor: t.c.line },
  rowMain: { flex: 1, gap: 2, minWidth: 0 },
  figures: { alignItems: 'flex-end', gap: 2, minWidth: 92 },
  timeline: { paddingVertical: 4 },
  tlRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingVertical: 9 },
  tlWhen: { width: 66, marginTop: 1 },
  tlFoot: { paddingTop: 4, paddingBottom: 8 },
  nowRow: { flexDirection: 'row', alignItems: 'center', gap: 8, paddingVertical: 6 },
  nowLabel: { fontSize: 11.5 },
  nowLine: { flex: 1, height: 1, backgroundColor: t.c.fg3 },
  tray: { paddingBottom: 8 },
  trayBehind: {
    position: 'absolute',
    left: 8,
    right: 8,
    bottom: 3,
    height: 20,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: t.c.riskLine,
    backgroundColor: t.c.panel,
  },
  trayBehind2: { left: 16, right: 16, bottom: -1, opacity: 0.7 },
  trayCard: {
    gap: 4,
    padding: 12,
    borderRadius: radius.lg,
    borderWidth: 1,
    borderColor: t.c.riskLine,
    backgroundColor: t.c.panel,
    ...t.shadow.sm,
  },
  trayHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  trayDot: { width: 7, height: 7, borderRadius: 2, backgroundColor: t.c.risk },
  trayFoot: { flexDirection: 'row', alignItems: 'center', marginTop: 4 },
  nextOpen: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  dayChange: { flexDirection: 'row', alignItems: 'baseline', gap: 6, flexWrap: 'wrap' },
}));
