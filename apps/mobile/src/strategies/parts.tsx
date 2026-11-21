import { router } from 'expo-router';
import { Blocks, ChevronRight, Plus } from 'lucide-react-native';
import type { ReactNode } from 'react';
import { Pressable, View } from 'react-native';

import { HeaderActions } from '../shell/HeaderActions';
import { makeStyles, radius, useTheme } from '../theme';
import { CopilotMark, Text } from '../ui';

/** A small outlined LIVE or PAPER tag; paper and live are always labelled. */
export function ModeTag({ mode }: { mode: 'live' | 'paper' }) {
  const s = useStyles();
  return (
    <View style={[s.tag, mode === 'live' ? s.tagLive : null]}>
      <Text variant="numSmall" tone={mode === 'live' ? 'fg' : 'fg2'} style={s.tagText}>{mode === 'live' ? 'LIVE' : 'PAPER'}</Text>
    </View>
  );
}

/** A round ink button with a plus, then the bell and avatar. */
export function NewStrategyActions() {
  const s = useStyles();
  const { c } = useTheme();
  return (
    <View style={s.actions}>
      <Pressable accessibilityRole="button" accessibilityLabel="New strategy" onPress={() => router.push('/builder/new')} style={s.plus} hitSlop={6}>
        <Plus color={c.canvas} size={18} strokeWidth={2} />
      </Pressable>
      <HeaderActions />
    </View>
  );
}

/** One row of a grouped card: an icon, a title and a line under it, and a chevron. */
export function WayRow({ icon, title, sub, onPress, last = false }: { icon: ReactNode; title: string; sub: string; onPress: () => void; last?: boolean }) {
  const s = useStyles();
  const { c } = useTheme();
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [s.way, last ? null : s.wayDivider, pressed ? s.pressed : null]}>
      <View style={s.wayIcon}>{icon}</View>
      <View style={s.wayText}>
        <Text variant="bodyStrong">{title}</Text>
        <Text variant="small" tone="fg3">{sub}</Text>
      </View>
      <ChevronRight color={c.fg3} size={16} strokeWidth={1.8} />
    </Pressable>
  );
}

export function CopilotIcon() {
  return <CopilotMark size={16} />;
}

export function BlocksIcon() {
  const { c } = useTheme();
  return <Blocks color={c.accent} size={16} strokeWidth={1.8} />;
}

/** The empty stage track: Draft, Backtested, Paper, Live, with nothing on it yet. */
export function StageTrack({ note }: { note: string }) {
  const s = useStyles();
  const stages = ['Draft', 'Backtested', 'Paper', 'Live'];
  return (
    <View style={s.track}>
      <View style={s.trackLine}>
        <View style={s.trackRule} />
        {stages.map((st) => (
          <View key={st} style={s.trackStop}>
            <View style={s.trackDot} />
          </View>
        ))}
      </View>
      <View style={s.trackLabels}>
        {stages.map((st) => (
          <Text key={st} variant="caption" tone="fg3">{st}</Text>
        ))}
      </View>
      <Text variant="caption" tone="fg3" style={s.trackNote}>{note}</Text>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  tag: { borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.xs, paddingHorizontal: 6, paddingVertical: 1 },
  tagLive: { borderColor: t.c.fg },
  tagText: { fontSize: 10.5, letterSpacing: 0.4 },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  plus: { width: 32, height: 32, borderRadius: 16, backgroundColor: t.c.fg, alignItems: 'center', justifyContent: 'center' },
  way: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 },
  wayDivider: { borderBottomWidth: 1, borderColor: t.c.line },
  wayIcon: { width: 22, alignItems: 'center' },
  wayText: { flex: 1, gap: 1 },
  pressed: { opacity: 0.7 },
  track: { borderWidth: 1, borderStyle: 'dashed', borderColor: t.c.lineStrong, borderRadius: radius.md, padding: 14, gap: 8, backgroundColor: t.c.canvas },
  trackLine: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', height: 10 },
  trackRule: { position: 'absolute', left: 4, right: 4, top: 4.5, borderTopWidth: 1, borderStyle: 'dashed', borderColor: t.c.lineStrong },
  trackStop: { width: 9, alignItems: 'center' },
  trackDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: t.c.lineStrong },
  trackLabels: { flexDirection: 'row', justifyContent: 'space-between' },
  trackNote: { marginTop: 4 },
}));
