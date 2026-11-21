import { money, qty } from '@llamatrade/core/format';
import { router } from 'expo-router';
import { ChevronRight, X } from 'lucide-react-native';
import { Modal, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { openCopilot } from '../copilot/store';
import { makeStyles, radius, useTheme } from '../theme';
import { Button, CopilotMark, Text } from '../ui';
import type { FillIn, Mode } from './model';
import { PaperAmount } from './PaperAmount';
import { hm, longDate } from './when';

export interface DaySheetSubject {
  /** Start of the day the marker sits on. */
  day: number;
  /** The session the marker belongs to, or null for every session's fills that day. */
  session: { name: string; sessionId: string | null; mode: Mode } | null;
  fills: readonly FillIn[];
  /** Session name and mode for each fill, keyed by fill id. */
  owner: (f: FillIn) => { name: string; mode: Mode | null };
}

function isoDay(t: number): string {
  const d = new Date(t);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

/**
 * The fills behind a marker on the curve or a lane, with questions that open Copilot about
 * that day (layout2 A detail, copilot/entry2 A).
 */
export function DaySheet({ subject, onClose }: { subject: DaySheetSubject | null; onClose: () => void }) {
  const { c } = useTheme();
  const s = useStyles();
  const insets = useSafeAreaInsets();
  const open = subject !== null;
  const fills = subject?.fills ?? [];
  const title =
    fills.length === 0 ? 'No fills this day' : fills.length === 1 ? '1 fill' : `${fills.length} fills`;
  const ask = (question: string) => {
    if (!subject) return;
    const id = subject.session?.sessionId;
    onClose();
    openCopilot(id ? { kind: 'marker', id, date: isoDay(subject.day) } : { kind: 'account', id: 'account', date: isoDay(subject.day) }, {
      question,
    });
  };
  const questions = subject?.session
    ? [`Why did ${subject.session.name} trade on ${longDate(subject.day)}?`, 'What did these fills cost against the prices at the open?']
    : [`What did my sessions do on ${longDate(subject?.day ?? 0)}?`];
  return (
    <Modal visible={open} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={s.scrim} onPress={onClose} accessibilityLabel="Close" />
      <View style={[s.sheet, { paddingBottom: insets.bottom + 16 }]}>
        <View style={s.grab} />
        <View style={s.head}>
          <View style={s.flex}>
            <Text variant="label" tone="fg3">
              {subject ? longDate(subject.day).toUpperCase() : ''}
              {subject?.session ? ` · ${subject.session.name.toUpperCase()}` : ''}
            </Text>
            <Text variant="heading">{title}</Text>
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel="Close" onPress={onClose} hitSlop={10}>
            <X color={c.fg3} size={20} strokeWidth={1.8} />
          </Pressable>
        </View>
        <ScrollView style={s.list} contentContainerStyle={s.listBody}>
          {fills.map((f, i) => {
            const who = subject?.owner(f);
            return (
              <View key={f.id} style={[s.fill, i < fills.length - 1 ? s.divider : null]}>
                <View style={s.tag}>
                  <Text variant="numSmall" tone="fg2" style={s.tagText}>
                    {f.side === 'buy' ? 'BUY' : 'SELL'}
                  </Text>
                </View>
                <View style={s.flex}>
                  <Text variant="small">
                    {qty(f.qty)} {f.symbol} at {money(f.price, 2)}
                  </Text>
                  <Text variant="caption" tone="fg3">
                    {[who?.name, who?.mode, hm(f.t)].filter(Boolean).join(' · ')}
                  </Text>
                </View>
                <PaperAmount paper={who?.mode === 'paper'} variant="numSmall">
                  {money(f.qty * f.price, 2)}
                </PaperAmount>
              </View>
            );
          })}
        </ScrollView>
        <View style={s.questions}>
          {questions.map((q) => (
            <Pressable key={q} accessibilityRole="button" onPress={() => ask(q)} style={({ pressed }) => [s.question, pressed ? s.pressed : null]}>
              <CopilotMark size={16} />
              <Text variant="small" style={s.flex}>
                {q}
              </Text>
              <ChevronRight color={c.fg3} size={16} strokeWidth={1.8} />
            </Pressable>
          ))}
        </View>
        <Button
          label="Open activity"
          onPress={() => {
            onClose();
            router.push('/portfolio/activity');
          }}
        />
      </View>
    </Modal>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  pressed: { opacity: 0.7 },
  scrim: { flex: 1, backgroundColor: 'rgba(0,0,0,0.35)' },
  sheet: {
    backgroundColor: t.c.panel,
    borderTopLeftRadius: radius.sheet,
    borderTopRightRadius: radius.sheet,
    paddingHorizontal: 20,
    paddingTop: 8,
    gap: 12,
    maxHeight: '78%',
    ...t.shadow.lg,
  },
  grab: { alignSelf: 'center', width: 36, height: 4, borderRadius: 2, backgroundColor: t.c.lineStrong, marginBottom: 4 },
  head: { flexDirection: 'row', alignItems: 'flex-start', gap: 12 },
  list: { flexGrow: 0 },
  listBody: { paddingBottom: 2 },
  fill: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  tag: { minWidth: 40, alignItems: 'center', borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.xs, paddingVertical: 1 },
  tagText: { fontSize: 10.5, lineHeight: 14 },
  questions: { borderTopWidth: 1, borderColor: t.c.line },
  question: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 12, borderBottomWidth: 1, borderColor: t.c.line },
}));
