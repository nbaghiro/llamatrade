import type { Timestamp } from '@llamatrade/core/proto/common_pb';
import { MessageRole, useAgentStore, type AgentMessage } from '@llamatrade/core/stores/agent';
import { Check, History, Send, Sparkles, X } from 'lucide-react-native';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import {
  ActivityIndicator,
  Animated,
  Easing,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ArtifactCard } from '../../src/copilot/ArtifactCard';
import { HistorySheet } from '../../src/copilot/HistorySheet';
import { Markdown } from '../../src/copilot/Markdown';
import { ThinkingBlock } from '../../src/copilot/ThinkingBlock';
import { fonts, makeStyles, radius, space, useTheme } from '../../src/theme';
import { Button, Card, Notice, ScreenHeader, Text } from '../../src/ui';

const DEFAULT_PROMPTS = [
  'Build a momentum rotation across the 11 sector ETFs, monthly',
  'How is my portfolio doing?',
  'Add a bond hedge below the 200-day',
];

function fmtTime(ts?: Timestamp): string {
  const d = ts?.seconds ? new Date(Number(ts.seconds) * 1000) : new Date();
  return `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** Human labels for confirmation-gated tools; falls back to the de-underscored name. */
const TOOL_LABELS: Record<string, string> = { run_backtest: 'Run a backtest' };
function humanizeTool(name: string): string {
  return TOOL_LABELS[name] ?? name.replace(/_/g, ' ');
}

/** Drops the raw strategy DSL fence from prose; the artifact card shows it instead. */
function stripStrategyFences(content: string): string {
  return content
    .replace(/```[a-z]*\n?[\s\S]*?```/gi, (block) => (/\(\s*strategy/i.test(block) ? '' : block))
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function Dot({ delay }: { delay: number }) {
  const { c } = useTheme();
  const v = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    const a = Animated.loop(
      Animated.sequence([
        Animated.timing(v, { toValue: 1, duration: 300, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
        Animated.timing(v, { toValue: 0, duration: 300, easing: Easing.inOut(Easing.ease), useNativeDriver: true }),
      ]),
    );
    const t = setTimeout(() => a.start(), delay);
    return () => {
      clearTimeout(t);
      a.stop();
    };
  }, [v, delay]);
  return (
    <Animated.View
      style={{
        width: 6,
        height: 6,
        borderRadius: 3,
        backgroundColor: c.fg3,
        opacity: v.interpolate({ inputRange: [0, 1], outputRange: [0.35, 1] }),
      }}
    />
  );
}

function Bubble({ me, time, children }: { me: boolean; time?: string; children: ReactNode }) {
  const s = useStyles();
  return (
    <View style={[s.msg, me ? s.msgMe : null]}>
      <View style={[s.bubble, me ? s.bubbleMe : s.bubbleAi]}>{children}</View>
      {time ? <Text variant="caption" tone="fg3" style={me ? s.timeMe : null}>{time}</Text> : null}
    </View>
  );
}

function ToolRow({ name, status }: { name: string; status: 'running' | 'complete' | 'error' }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <View style={s.tool}>
      {status === 'running' ? (
        <ActivityIndicator size="small" color={c.fg3} />
      ) : status === 'complete' ? (
        <Check color={c.accent} size={13} strokeWidth={2} />
      ) : (
        <X color={c.risk} size={13} strokeWidth={2} />
      )}
      <Text variant="numSmall" tone={status === 'error' ? 'risk' : 'fg2'} numberOfLines={1} style={s.toolName}>
        {name}
      </Text>
      <Text variant="caption" tone="fg3">{status === 'running' ? 'Running' : status === 'complete' ? 'Done' : 'Failed'}</Text>
    </View>
  );
}

export default function CopilotScreen() {
  const { c, mode } = useTheme();
  const s = useStyles();
  const {
    messages,
    pendingArtifacts,
    isStreaming,
    streamingContent,
    thinkingContent,
    currentToolCall,
    pendingArtifactIdsForCurrentMessage,
    pendingConfirmation,
    suggestedPrompts,
    error,
    serviceUnavailable,
    loadSessions,
    sendMessage,
    confirmToolCall,
    getSuggestedPrompts,
    clearError,
  } = useAgentStore();

  const [draft, setDraft] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    getSuggestedPrompts({ page: 'copilot' });
    loadSessions();
  }, [getSuggestedPrompts, loadSessions]);

  const prompts = suggestedPrompts.length ? suggestedPrompts.slice(0, 4) : DEFAULT_PROMPTS;
  const artifactFor = (id: string) => pendingArtifacts.find((a) => a.id === id);

  const send = (text: string) => {
    const t = text.trim();
    if (!t || isStreaming || serviceUnavailable) return;
    setDraft('');
    sendMessage(t, undefined, undefined, 'copilot');
  };

  const empty = messages.length === 0 && !isStreaming;
  const canSend = !!draft.trim() && !isStreaming && !serviceUnavailable;

  return (
    <SafeAreaView edges={['top']} style={s.safe}>
      <View style={s.header}>
        <ScreenHeader
          title="Copilot"
          right={
            <Pressable accessibilityLabel="Conversation history" onPress={() => setHistoryOpen(true)} hitSlop={10}>
              <History color={c.fg2} size={20} strokeWidth={1.6} />
            </Pressable>
          }
        />
      </View>

      <KeyboardAvoidingView style={s.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={s.body}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
          keyboardShouldPersistTaps="handled"
        >
          {serviceUnavailable ? (
            <Notice
              title="Copilot is unavailable."
              detail="Your conversations are still here. Sending is paused until the service is back."
            />
          ) : null}

          {error ? <Notice title="Something went wrong." detail={`${error} Tap to dismiss.`} onPress={clearError} /> : null}

          {empty ? (
            <View style={s.emptyWrap}>
              <View style={s.emptyIcon}>
                <Sparkles color={c.accent} size={20} strokeWidth={1.6} />
              </View>
              <Text variant="heading" style={s.center}>Ask about a strategy</Text>
              <Text variant="small" tone="fg2" style={s.center}>
                Describe, build, edit or explain a strategy. It runs on your paper account.
              </Text>
              <View style={s.prompts}>
                {prompts.map((p) => (
                  <Card key={p} onPress={() => send(p)}>
                    <Text variant="small">{p}</Text>
                  </Card>
                ))}
              </View>
            </View>
          ) : (
            <>
              {messages.map((m: AgentMessage) => {
                const isUser = m.role === MessageRole.USER;
                return (
                  <View key={m.id} style={s.turn}>
                    {!isUser && m.thinking ? <ThinkingBlock content={m.thinking} autoExpanded={false} /> : null}
                    <Bubble me={isUser} time={fmtTime(m.createdAt)}>
                      <Markdown content={m.inlineArtifactIds.length ? stripStrategyFences(m.content) : m.content} />
                    </Bubble>
                    {m.inlineArtifactIds.map((id) => {
                      const a = artifactFor(id);
                      return a ? <ArtifactCard key={id} artifact={a} /> : null;
                    })}
                  </View>
                );
              })}

              {currentToolCall ? <ToolRow name={currentToolCall.name} status={currentToolCall.status} /> : null}

              {pendingArtifactIdsForCurrentMessage.map((id) => {
                const a = artifactFor(id);
                return a ? <ArtifactCard key={`live-${id}`} artifact={a} /> : null;
              })}

              {!isStreaming && pendingConfirmation ? (
                <View style={s.turn}>
                  <Card style={s.approve}>
                    <Text variant="label" tone="fg3">Approve action</Text>
                    <Text variant="subhead">{humanizeTool(pendingConfirmation.toolName)}</Text>
                  </Card>
                  <Button label="Approve and run" onPress={() => confirmToolCall(true)} />
                  <Button label="Decline" variant="secondary" onPress={() => confirmToolCall(false)} />
                </View>
              ) : null}

              {isStreaming && thinkingContent ? (
                <ThinkingBlock content={thinkingContent} autoExpanded={streamingContent.length === 0} streaming />
              ) : null}

              {isStreaming ? (
                streamingContent ? (
                  <Bubble me={false}>
                    <Markdown content={stripStrategyFences(streamingContent)} />
                  </Bubble>
                ) : currentToolCall ? null : (
                  <View style={[s.bubble, s.bubbleAi, s.typing]}>
                    <Dot delay={0} />
                    <Dot delay={150} />
                    <Dot delay={300} />
                  </View>
                )
              ) : null}
            </>
          )}
        </ScrollView>

        <View style={s.composer}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder={serviceUnavailable ? 'Copilot is unavailable' : 'Message Copilot'}
            placeholderTextColor={c.fg3}
            editable={!serviceUnavailable}
            multiline
            keyboardAppearance={mode}
            selectionColor={c.accent}
            style={s.input}
          />
          <Pressable
            accessibilityRole="button"
            accessibilityLabel="Send"
            onPress={() => send(draft)}
            disabled={!canSend}
            style={[s.send, canSend ? null : s.sendOff]}
          >
            {isStreaming ? (
              <ActivityIndicator size="small" color={c.accentInk} />
            ) : (
              <Send color={c.accentInk} size={16} strokeWidth={1.8} />
            )}
          </Pressable>
        </View>
      </KeyboardAvoidingView>

      <HistorySheet visible={historyOpen} onClose={() => setHistoryOpen(false)} />
    </SafeAreaView>
  );
}

const useStyles = makeStyles((t) => ({
  safe: { flex: 1, backgroundColor: t.c.canvas },
  flex: { flex: 1 },
  header: { paddingHorizontal: space.gutter, paddingTop: 10, paddingBottom: 6 },
  body: { paddingHorizontal: space.gutter, paddingTop: 6, paddingBottom: 20, gap: space.gap },
  emptyWrap: { alignItems: 'center', gap: 8, paddingTop: 36 },
  emptyIcon: {
    width: 52,
    height: 52,
    borderRadius: 26,
    borderWidth: 1,
    borderStyle: 'dashed',
    borderColor: t.c.lineStrong,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: 8,
  },
  center: { textAlign: 'center' },
  prompts: { alignSelf: 'stretch', gap: 10, marginTop: 18 },
  turn: { gap: 10 },
  msg: { alignSelf: 'flex-start', maxWidth: '88%', gap: 4 },
  msgMe: { alignSelf: 'flex-end', maxWidth: '80%' },
  timeMe: { textAlign: 'right' },
  bubble: { borderRadius: radius.sm, paddingHorizontal: 12, paddingVertical: 8 },
  bubbleMe: { backgroundColor: t.c.sunk },
  bubbleAi: { backgroundColor: t.c.panel, borderWidth: 1, borderColor: t.c.line },
  typing: { alignSelf: 'flex-start', flexDirection: 'row', gap: 5, paddingVertical: 12 },
  tool: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  toolName: { flexShrink: 1 },
  approve: { gap: 4 },
  composer: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    gap: 10,
    paddingHorizontal: 14,
    paddingTop: 10,
    paddingBottom: 10,
    borderTopWidth: 1,
    borderColor: t.c.line,
    backgroundColor: t.c.canvas,
  },
  input: {
    flex: 1,
    minHeight: 42,
    maxHeight: 120,
    borderRadius: 21,
    borderWidth: 1,
    borderColor: t.c.lineStrong,
    backgroundColor: t.c.panel,
    paddingHorizontal: 16,
    paddingTop: 11,
    paddingBottom: 11,
    fontFamily: fonts.sans,
    fontSize: 15,
    color: t.c.fg,
  },
  send: {
    width: 40,
    height: 40,
    borderRadius: 20,
    marginBottom: 1,
    backgroundColor: t.c.accentFill,
    alignItems: 'center',
    justifyContent: 'center',
  },
  sendOff: { opacity: 0.45 },
}));
