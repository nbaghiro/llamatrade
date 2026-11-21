import { useAgentStore } from '@llamatrade/core/stores/agent';
import { router } from 'expo-router';
import { ArrowUp, Clock } from 'lucide-react-native';
import { useState } from 'react';
import { ActivityIndicator, Pressable, TextInput, View } from 'react-native';

import { fonts, makeStyles, radius, useTheme } from '../theme';
import { ListRow, Text } from '../ui';
import { copilotLimit, limitCopy } from './limits';
import { useCopilotUi } from './store';
import { askPlaceholder, type CopilotSubject } from './subjects';

/** The composer, scoped to a subject: "Ask about Recession Radar". */
export function Composer({ subject, onSend }: { subject: CopilotSubject; onSend: (text: string) => void }) {
  const { c, mode } = useTheme();
  const s = useStyles();
  const [draft, setDraft] = useState('');
  const isStreaming = useAgentStore((st) => st.isStreaming);
  const canSend = !!draft.trim() && !isStreaming;
  const send = () => {
    if (!canSend) return;
    onSend(draft);
    setDraft('');
  };
  return (
    <View style={s.wrap}>
      <TextInput
        value={draft}
        onChangeText={setDraft}
        placeholder={askPlaceholder(subject)}
        placeholderTextColor={c.fg3}
        multiline
        keyboardAppearance={mode}
        selectionColor={c.accent}
        style={s.input}
      />
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Send"
        onPress={send}
        disabled={!canSend}
        style={[s.send, canSend ? s.sendOn : null]}
      >
        {isStreaming ? (
          <ActivityIndicator size="small" color={c.fg3} />
        ) : (
          <ArrowUp color={canSend ? c.accentInk : c.fg3} size={17} strokeWidth={2} />
        )}
      </Pressable>
    </View>
  );
}

/** True when Copilot can't take a message now. */
export function useCopilotLimit() {
  const serviceUnavailable = useAgentStore((st) => st.serviceUnavailable);
  const error = useAgentStore((st) => st.error);
  return copilotLimit({ serviceUnavailable, error });
}

/**
 * In the composer's place when Copilot can't answer (limits B): why, the kept question marked
 * not sent, and what still covers the need without the model.
 */
export function LimitPanel({ subject, onRetry }: { subject: CopilotSubject; onRetry: (text: string) => void }) {
  const { c } = useTheme();
  const s = useStyles();
  const limit = useCopilotLimit();
  const unsent = useCopilotUi((st) => st.unsent);
  const downSince = useCopilotUi((st) => st.downSince);
  if (!limit) return null;
  const copy = limitCopy(limit, downSince, !!unsent);
  return (
    <View style={s.limit}>
      <View style={s.notice}>
        <View style={s.noticeHead}>
          <Clock color={c.risk} size={15} strokeWidth={1.8} />
          <Text variant="smallStrong" style={s.flex}>{copy.title}</Text>
        </View>
        <Text variant="small" tone="fg2">{copy.body}</Text>
      </View>
      {unsent ? (
        <View style={s.unsent}>
          <Text variant="body">{unsent.text}</Text>
          <View style={s.unsentFoot}>
            <Text variant="caption" tone="fg3">Not sent</Text>
            <Text variant="smallStrong" tone="accent" onPress={() => onRetry(unsent.text)}>Try again</Text>
          </View>
        </View>
      ) : null}
      <Text variant="subhead">Still works</Text>
      <View style={s.list}>
        {subject.kind === 'session' ? (
          <ListRow label={subject.name} sub="Holdings, rule and schedule" onPress={() => router.push(`/sessions/${subject.id}`)} />
        ) : subject.kind === 'strategy' ? (
          <ListRow label={subject.name} sub="Rule and backtests" onPress={() => router.push(`/strategy/${subject.id}`)} />
        ) : (
          <ListRow label="Portfolio" sub="Holdings and activity" onPress={() => router.push('/portfolio')} />
        )}
        <ListRow label="Strategies" sub="Templates and backtests" onPress={() => router.push('/(tabs)/strategies')} />
        <ListRow label="Past conversations" sub="Readable as usual" onPress={() => router.push('/copilot/history')} last />
      </View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  wrap: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 8,
    borderWidth: 1,
    borderColor: t.c.lineStrong,
    backgroundColor: t.c.panel,
    borderRadius: 24,
    paddingLeft: 16,
    paddingRight: 5,
    paddingVertical: 5,
    ...t.shadow.sm,
  },
  input: {
    flex: 1,
    minHeight: 38,
    maxHeight: 120,
    paddingTop: 9,
    paddingBottom: 9,
    fontFamily: fonts.sans,
    fontSize: 15,
    color: t.c.fg,
  },
  send: { width: 38, height: 38, borderRadius: 19, backgroundColor: t.c.sunk, alignItems: 'center', justifyContent: 'center' },
  sendOn: { backgroundColor: t.c.accentFill },
  limit: { gap: 14 },
  notice: { borderWidth: 1, borderColor: t.c.riskLine, backgroundColor: t.c.panel, borderRadius: radius.lg, padding: 14, gap: 6 },
  noticeHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  unsent: { borderWidth: 1, borderStyle: 'dashed', borderColor: t.c.lineStrong, backgroundColor: t.c.sunk, borderRadius: radius.lg, padding: 14, gap: 8 },
  unsentFoot: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  list: { backgroundColor: t.c.panel, borderWidth: 1, borderColor: t.c.line, borderRadius: radius.lg, paddingHorizontal: 16 },
}));
