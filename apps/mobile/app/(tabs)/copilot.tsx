import { useAgentStore } from '@llamatrade/core/stores/agent';
import { router, useIsFocused } from 'expo-router';
import { History, Plus } from 'lucide-react-native';
import { useEffect, useRef } from 'react';
import { KeyboardAvoidingView, Platform, Pressable, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { Composer, LimitPanel, useCopilotLimit } from '../../src/copilot/Composer';
import { looksLikeDraft } from '../../src/copilot/draftQuestions';
import { sendToCopilot, startDraft, takePendingQuestion, useCopilotUi } from '../../src/copilot/store';
import { QuestionList, SubjectCard, SubjectChips } from '../../src/copilot/SubjectParts';
import type { CopilotSubject } from '../../src/copilot/subjects';
import { Thread } from '../../src/copilot/Thread';
import { useCurrentSubject } from '../../src/copilot/useSubjects';
import { makeStyles, space, useTheme } from '../../src/theme';
import { Canvas, Notice, Text } from '../../src/ui';

/** The Copilot tab (page2 A): choose what to ask about, see what Copilot reads, then ask. */
export default function CopilotScreen() {
  const { c } = useTheme();
  const s = useStyles();
  const focused = useIsFocused();
  const { subject, subjects } = useCurrentSubject();
  const messages = useAgentStore((st) => st.messages);
  const isStreaming = useAgentStore((st) => st.isStreaming);
  const error = useAgentStore((st) => st.error);
  const clearError = useAgentStore((st) => st.clearError);
  const sheet = useCopilotUi((st) => st.sheet);
  const pending = useCopilotUi((st) => st.pending);
  const limit = useCopilotLimit();
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    useAgentStore.getState().loadSessions().catch(() => undefined);
  }, []);

  useEffect(() => {
    if (focused && sheet !== 'closed') useCopilotUi.getState().setSheet('closed');
  }, [focused, sheet]);

  const ask = (text: string) => {
    sendToCopilot(text, subject, 'copilot').catch(() => undefined);
  };

  const typed = (text: string) => {
    if (!looksLikeDraft(text)) return ask(text);
    startDraft(text, subject).catch(() => undefined);
    router.push('/copilot/draft');
  };

  useEffect(() => {
    if (!focused || sheet !== 'closed' || !pending) return;
    const q = takePendingQuestion();
    if (q) sendToCopilot(q, subject, 'copilot').catch(() => undefined);
  }, [focused, sheet, pending, subject]);

  const choose = (next: CopilotSubject) => {
    if (next.key === subject.key) return;
    useCopilotUi.getState().setContext(next.kind === 'account' ? null : { kind: next.kind, id: next.id });
    if (useAgentStore.getState().messages.length) useAgentStore.getState().startNewChat();
  };

  const empty = messages.length === 0 && !isStreaming;

  return (
    <Canvas art="bold" artSeed="copilot-ask">
      <SafeAreaView edges={['top']} style={s.flex}>
        <View style={s.header}>
          <Text variant="title">Copilot</Text>
          <View style={s.actions}>
            <Pressable accessibilityLabel="Earlier conversations" hitSlop={10} onPress={() => router.push('/copilot/history')}>
              <History color={c.fg} size={22} strokeWidth={1.6} />
            </Pressable>
            <Pressable
              accessibilityLabel="New conversation"
              hitSlop={10}
              onPress={() => useAgentStore.getState().startNewChat()}
            >
              <Plus color={c.fg} size={24} strokeWidth={1.6} />
            </Pressable>
          </View>
        </View>
        <SubjectChips subjects={subjects} selected={subject.key} onSelect={choose} />

        <KeyboardAvoidingView style={s.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
          <ScrollView
            ref={scrollRef}
            contentContainerStyle={s.body}
            keyboardShouldPersistTaps="handled"
            onContentSizeChange={() => (empty ? null : scrollRef.current?.scrollToEnd({ animated: true }))}
          >
            {error && !limit ? <Notice title="That message didn't go through." detail={`${error} Tap to dismiss.`} onPress={clearError} /> : null}
            {empty && !limit ? (
              <>
                <SubjectCard subject={subject} />
                <QuestionList subject={subject} onAsk={ask} />
              </>
            ) : null}
            {!empty ? <Thread subject={subject} onAsk={ask} /> : null}
            {limit ? <LimitPanel subject={subject} onRetry={ask} /> : null}
          </ScrollView>
          {limit ? null : (
            <View style={s.composer}>
              <Composer subject={subject} onSend={typed} />
            </View>
          )}
        </KeyboardAvoidingView>
      </SafeAreaView>
    </Canvas>
  );
}

const useStyles = makeStyles(() => ({
  flex: { flex: 1 },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: space.gutter,
    paddingTop: 10,
    paddingBottom: 12,
  },
  actions: { flexDirection: 'row', alignItems: 'center', gap: 18 },
  body: { paddingHorizontal: space.gutter, paddingTop: 14, paddingBottom: 24, gap: 18 },
  composer: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 10 },
}));
