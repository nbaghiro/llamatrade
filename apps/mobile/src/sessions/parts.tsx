import { ChevronRight, Snowflake, TriangleAlert } from 'lucide-react-native';
import { useState } from 'react';
import { Pressable, View, type LayoutChangeEvent } from 'react-native';
import Svg, { Circle, Line, Rect } from 'react-native-svg';

import { fonts, makeStyles, radius, useTheme } from '../theme';
import { Text } from '../ui';
import type { LaneMark, Mode, NeedsItem } from './model';

/** LIVE in a solid ink pill, PAPER in a dashed outline, so the mode reads at a glance. */
export function ModeTag({ mode }: { mode: Mode }) {
  const { c } = useTheme();
  const s = useStyles();
  const live = mode === 'live';
  return (
    <View style={[s.tag, live ? { backgroundColor: c.fg, borderColor: c.fg } : { borderColor: c.lineStrong, borderStyle: 'dashed' }]}>
      <Text variant="caption" color={live ? c.canvas : c.fg2} style={s.tagText}>
        {live ? 'LIVE' : 'PAPER'}
      </Text>
    </View>
  );
}

/** The amber card that lists everything waiting on a decision, one row each. */
export function NeedsCard({ items, onOpen }: { items: readonly NeedsItem[]; onOpen: (item: NeedsItem) => void }) {
  const { c } = useTheme();
  const s = useStyles();
  if (items.length === 0) return null;
  return (
    <View style={[s.needs, { borderColor: c.riskLine }]}>
      {items.map((item, i) => {
        const Icon = item.kind === 'frozen' ? Snowflake : TriangleAlert;
        return (
          <Pressable
            key={item.id}
            accessibilityRole="button"
            onPress={() => onOpen(item)}
            style={({ pressed }) => [s.needsRow, i > 0 ? { borderTopWidth: 1, borderColor: c.riskLine } : null, pressed ? { opacity: 0.7 } : null]}
          >
            <Icon color={c.risk} size={17} strokeWidth={1.8} />
            <View style={s.flex}>
              <Text variant="bodyStrong" numberOfLines={1}>{item.title}</Text>
              {item.detail ? <Text variant="small" tone="fg2" numberOfLines={1}>{item.detail}</Text> : null}
            </View>
            <ChevronRight color={c.fg3} size={16} strokeWidth={1.8} />
          </Pressable>
        );
      })}
    </View>
  );
}

export interface LaneProps {
  /** 0..1 where the lane begins (the session's start); defaults to the left edge. */
  from?: number;
  /** 0..1 where the lane ends; 1 is now. */
  to?: number;
  marks?: readonly LaneMark[];
  /** A square at `to` for a session that stopped. */
  stopped?: boolean;
  /** The whole lane in amber, for a frozen session. */
  attention?: boolean;
  /** Numbered badge on the last mark, e.g. today's fill count. */
  badge?: number;
  /** A vertical tick for now at the right edge. */
  now?: boolean;
  /** Draw buys filled and sells hollow; otherwise every mark is a hollow rebalance ring. */
  sided?: boolean;
  height?: number;
  muted?: boolean;
}

/** One horizontal lane: a start tick, a line to now and a mark per rebalance or fill. */
export function Lane({ from = 0, to = 1, marks = [], stopped = false, attention = false, badge, now = false, sided = false, height = 18, muted = false }: LaneProps) {
  const { c } = useTheme();
  const [w, setW] = useState(0);
  const onLayout = (e: LayoutChangeEvent) => setW(Math.round(e.nativeEvent.layout.width));
  const pad = 7;
  const x = (f: number) => pad + (w - pad * 2) * f;
  const y = height / 2;
  const tone = attention ? c.risk : muted ? c.fg3 : c.accent;
  const last = marks.length ? marks[marks.length - 1] : null;
  return (
    <View onLayout={onLayout} style={{ height }}>
      {w > 0 ? (
        <Svg width={w} height={height}>
          <Line x1={x(from)} x2={x(to)} y1={y} y2={y} stroke={tone} strokeOpacity={muted ? 0.6 : 0.7} strokeWidth={attention ? 2.5 : 1.5} />
          <Rect x={x(from) - 1.25} y={y - 6} width={2.5} height={12} rx={1} fill={tone} />
          {marks.map((m, i) => {
            const filled = sided ? m.side === 'buy' : false;
            const isBadge = badge !== undefined && m === last;
            return (
              <Circle
                key={i}
                cx={x(m.x)}
                cy={y}
                r={isBadge ? 7.5 : 4.5}
                fill={filled || isBadge ? tone : c.panel}
                stroke={tone}
                strokeWidth={1.4}
              />
            );
          })}
          {stopped ? <Rect x={x(to) - 5} y={y - 5} width={10} height={10} rx={2} fill={c.fg3} /> : null}
          {now ? <Line x1={w - pad} x2={w - pad} y1={0} y2={height} stroke={c.fg} strokeWidth={1.25} /> : null}
        </Svg>
      ) : null}
      {w > 0 && badge !== undefined && last ? (
        <View pointerEvents="none" style={{ position: 'absolute', left: x(last.x) - 7.5, top: y - 7.5, width: 15, height: 15, alignItems: 'center', justifyContent: 'center' }}>
          <Text variant="caption" color={c.panel} style={{ fontFamily: fonts.monoSemibold, fontSize: 9, lineHeight: 11 }}>
            {badge}
          </Text>
        </View>
      ) : null}
    </View>
  );
}

/** A labelled lane under a chart: a short mono label on the left, the lane beside it. */
export function LabelledLane({ label, note, ...lane }: LaneProps & { label: string; note?: string }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <View style={[s.labelled, { borderColor: c.line }]}>
      <Text variant="numSmall" tone={lane.attention ? 'risk' : 'fg3'} style={s.laneLabel} numberOfLines={1}>
        {label}
      </Text>
      <View style={s.flex}>
        <Lane {...lane} />
      </View>
      {note ? <Text variant="numSmall" tone="risk" style={s.laneNote}>{note}</Text> : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1, minWidth: 0 },
  tag: { borderWidth: 1, borderRadius: radius.pill, paddingHorizontal: 7, height: 20, justifyContent: 'center', alignSelf: 'flex-start' },
  tagText: { fontFamily: fonts.semibold, fontSize: 10, lineHeight: 12, letterSpacing: 0.6 },
  needs: { backgroundColor: t.c.riskSoft, borderWidth: 1, borderRadius: radius.lg, paddingHorizontal: 14 },
  needsRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 },
  labelled: { flexDirection: 'row', alignItems: 'center', gap: 8, borderTopWidth: 1, paddingVertical: 3 },
  laneLabel: { width: 44, fontSize: 11 },
  laneNote: { fontSize: 11 },
}));
