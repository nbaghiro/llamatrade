import { ChartLine, Clock, FlaskConical, Info, Pencil, type LucideIcon } from 'lucide-react-native';
import { Pressable, ScrollView, View } from 'react-native';

import { makeStyles, radius, space, useTheme } from '../theme';
import { StatusMark, Text } from '../ui';
import { subjectQuestions, subjectReads, subjectStateLabel, type CopilotSubject, type QuestionIcon } from './subjects';

/** "Paper" dashed and "Live" solid, as everywhere money is shown. */
export function ModePill({ live }: { live: boolean }) {
  const s = useStyles();
  return (
    <View style={[s.mode, live ? s.modeLive : null]}>
      <Text variant="numSmall" tone={live ? 'fg' : 'fg2'} style={s.modeText}>{live ? 'LIVE' : 'PAPER'}</Text>
    </View>
  );
}

/** Account and each session as chips; the chosen one outlined in the accent. */
export function SubjectChips({
  subjects,
  selected,
  onSelect,
}: {
  subjects: readonly CopilotSubject[];
  selected: string;
  onSelect: (s: CopilotSubject) => void;
}) {
  const s = useStyles();
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.chipBar} contentContainerStyle={s.chips} keyboardShouldPersistTaps="handled">
      {subjects.map((sub) => {
        const on = sub.key === selected;
        const attention = sub.state === 'frozen' || sub.state === 'error';
        return (
          <Pressable
            key={sub.key}
            accessibilityRole="tab"
            accessibilityState={{ selected: on }}
            onPress={() => onSelect(sub)}
            style={[s.chip, on ? s.chipOn : null]}
          >
            {attention ? <View style={s.riskDot} /> : null}
            <Text variant="small" tone={on ? 'fg' : 'fg2'}>{sub.name}</Text>
          </Pressable>
        );
      })}
    </ScrollView>
  );
}

/** What the subject is now and what Copilot reads for it. */
export function SubjectCard({ subject, detail }: { subject: CopilotSubject; detail?: string }) {
  const s = useStyles();
  const runState = subject.state === 'backtested' || subject.state === 'untested' ? 'draft' : subject.state;
  return (
    <View style={s.card}>
      {subject.kind !== 'account' ? (
        <View style={s.cardHead}>
          {subject.kind === 'session' ? <ModePill live={!!subject.live} /> : null}
          {runState ? <StatusMark state={runState} label={subject.state ? subjectStateLabel(subject.state) : undefined} /> : null}
          <View style={s.flex} />
          {detail ? <Text variant="numSmall" tone="fg3">{detail}</Text> : subject.version ? <Text variant="numSmall" tone="fg3">v{subject.version}</Text> : null}
        </View>
      ) : null}
      <Text variant="small" tone="fg2">{subjectReads(subject)}</Text>
    </View>
  );
}

const ICONS: Record<QuestionIcon, LucideIcon> = { clock: Clock, why: Info, chart: ChartLine, draft: Pencil, test: FlaskConical };

/** Questions written for the subject's state, one tap to ask. */
export function QuestionList({ subject, onAsk, title = 'Questions for today' }: { subject: CopilotSubject; onAsk: (q: string) => void; title?: string }) {
  const { c } = useTheme();
  const s = useStyles();
  const questions = subjectQuestions(subject);
  return (
    <View style={s.qWrap}>
      <Text variant="subhead">{title}</Text>
      <View style={s.card}>
        {questions.map((q, i) => {
          const Icon = ICONS[q.icon];
          return (
            <Pressable
              key={q.text}
              accessibilityRole="button"
              onPress={() => onAsk(q.text)}
              style={({ pressed }) => [s.qRow, i < questions.length - 1 ? s.divider : null, pressed ? s.pressed : null]}
            >
              <Icon color={c.fg3} size={16} strokeWidth={1.7} />
              <Text variant="body" style={s.flex}>{q.text}</Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  mode: { borderWidth: 1, borderStyle: 'dashed', borderColor: t.c.lineStrong, borderRadius: radius.pill, paddingHorizontal: 9, height: 22, justifyContent: 'center' },
  modeLive: { borderStyle: 'solid', borderColor: t.c.fg2 },
  modeText: { fontSize: 10.5, letterSpacing: 0.8 },
  chipBar: { flexGrow: 0 },
  chips: { gap: 8, paddingHorizontal: space.gutter, paddingVertical: 2 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    height: 34,
    paddingHorizontal: 14,
    borderRadius: radius.pill,
    borderWidth: 1,
    borderColor: t.c.lineStrong,
    backgroundColor: t.c.panel,
  },
  chipOn: { borderColor: t.c.accent, backgroundColor: t.c.accentSoft },
  riskDot: { width: 6, height: 6, borderRadius: 2, backgroundColor: t.c.risk },
  card: { backgroundColor: t.c.panel, borderWidth: 1, borderColor: t.c.line, borderRadius: radius.lg, paddingHorizontal: 16, paddingVertical: 12, gap: 8 },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  qWrap: { gap: 10 },
  qRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, paddingVertical: 12 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  pressed: { opacity: 0.6 },
}));
