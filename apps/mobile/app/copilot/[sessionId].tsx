import { MessageRole, useAgentStore } from '@llamatrade/core/stores/agent';
import { router, useLocalSearchParams } from 'expo-router';
import { ChevronLeft } from 'lucide-react-native';
import { useEffect, useMemo, useRef, useState } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { datedCitations } from '../../src/copilot/citations';
import { CitedCurve } from '../../src/copilot/CitedCurve';
import { Composer, LimitPanel, useCopilotLimit } from '../../src/copilot/Composer';
import { sendToCopilot, useCopilotUi } from '../../src/copilot/store';
import { QuestionList, SubjectCard } from '../../src/copilot/SubjectParts';
import { Thread } from '../../src/copilot/Thread';
import { useCurrentSubject } from '../../src/copilot/useSubjects';
import { makeStyles, space, useTheme } from '../../src/theme';
import { Canvas, Text } from '../../src/ui';

/** Explaining one session with its sources, citations placed on its curve (explain2 A). */
export default function ExplainSession() {
  const { c } = useTheme();
  const s = useStyles();
  const { sessionId, q } = useLocalSearchParams<{ sessionId: string; q?: string }>();
  const { subject, sessions } = useCurrentSubject();
  const messages = useAgentStore((st) => st.messages);
  const isStreaming = useAgentStore((st) => st.isStreaming);
  const limit = useCopilotLimit();
  const [cite, setCite] = useState<number | null>(null);
  const asked = useRef(false);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => useCopilotUi.getState().setSheet('closed'), []);

  useEffect(() => {
    const ui = useCopilotUi.getState();
    if (ui.context?.kind !== 'session' || ui.context.id !== sessionId) {
      ui.setContext({ kind: 'session', id: sessionId });
      useAgentStore.getState().startNewChat();
    }
  }, [sessionId]);

  const ready = subject.kind === 'session' && subject.id === sessionId;
  useEffect(() => {
    if (!ready || !q || asked.current) return;
    asked.current = true;
    sendToCopilot(q, subject, 'copilot').catch(() => undefined);
  }, [ready, q, subject]);

  const session = sessions.find((x) => x.id === sessionId);
  const lastAnswer = [...messages].reverse().find((m) => m.role !== MessageRole.USER);
  const pins = useMemo(() => (lastAnswer ? datedCitations(lastAnswer.content, new Date()) : []), [lastAnswer]);
  const times = useMemo(() => session?.equity.map((p) => new Date(p.timestamp).getTime()) ?? [], [session]);
  const values = useMemo(() => session?.equity.map((p) => p.value) ?? [], [session]);
  const ask = (text: string) => {
    sendToCopilot(text, subject, 'copilot').catch(() => undefined);
  };
  const empty = messages.length === 0 && !isStreaming;
  const title = session?.name ?? 'Session';

  return (
    <Canvas art="bold" artSeed={`copilot-${sessionId}`}>
      <SafeAreaView edges={['top']} style={s.flex}>
        <View style={s.nav}>
          <Pressable accessibilityRole="link" accessibilityLabel="Back" onPress={() => router.back()} hitSlop={10} style={s.side}>
            <ChevronLeft color={c.fg} size={22} strokeWidth={1.8} />
          </Pressable>
          <Text variant="subhead" numberOfLines={1} style={s.title}>{title}</Text>
          <View style={s.side} />
        </View>
        <KeyboardAvoidingView style={s.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView
            ref={scrollRef}
            contentContainerStyle={s.body}
            keyboardShouldPersistTaps="handled"
            onContentSizeChange={() => (empty ? null : scrollRef.current?.scrollToEnd({ animated: true }))}
          >
            {empty && ready ? (
              <>
                <SubjectCard subject={subject} />
                <QuestionList subject={subject} onAsk={ask} title="Ask about this session" />
              </>
            ) : null}
            {!empty ? <Thread subject={subject} onAsk={ask} onCite={setCite} citeOn={cite} /> : null}
            {!empty && !isStreaming && lastAnswer && values.length > 1 ? (
              <CitedCurve title={`${title}, equity`} times={times} values={values} citations={pins} active={cite} onPin={setCite} />
            ) : null}
            {limit ? <LimitPanel subject={subject} onRetry={ask} /> : null}
          </ScrollView>
          {limit ? null : (
            <View style={s.composer}>
              <Composer subject={subject} onSend={ask} />
            </View>
          )}
        </KeyboardAvoidingView>
      </SafeAreaView>
    </Canvas>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  nav: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 12,
    borderBottomWidth: 1,
    borderColor: t.c.line,
  },
  side: { width: 44 },
  title: { flex: 1, textAlign: 'center' },
  body: { paddingHorizontal: space.gutter, paddingTop: 18, paddingBottom: 24, gap: 16 },
  composer: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 10 },
}));
