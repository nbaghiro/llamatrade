import { ArrowUp, History, Plus, Settings, Sparkles } from 'lucide-react-native';
import { useEffect, useRef, useState } from 'react';
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
  type ViewStyle,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ArtifactCard } from '../../src/copilot/ArtifactCard';
import { HistorySheet } from '../../src/copilot/HistorySheet';
import { Markdown } from '../../src/copilot/Markdown';
import { type ChatMessage, useAgentStore } from '../../src/stores/agent';
import { useAuthStore } from '../../src/stores/auth';
import { fonts, palette } from '../../src/theme';
import { Badge, Body, Mono } from '../../src/ui';

const DEFAULT_PROMPTS = [
  'Build a momentum rotation across the 11 sector ETFs, monthly',
  'How is my portfolio doing?',
  'Add a bond hedge below the 200-day',
];

/** Hard brutalist offset shadow (iOS). */
function hardShadow(color: string): ViewStyle {
  return { shadowColor: color, shadowOffset: { width: 4, height: 4 }, shadowOpacity: 1, shadowRadius: 0, elevation: 6 };
}

function fmtTime(ms: number): string {
  const d = new Date(ms);
  return `${d.getHours()}:${String(d.getMinutes()).padStart(2, '0')}`;
}

/** Drop the raw strategy-DSL fence from prose — the rich artifact card is the canonical preview. */
function stripStrategyFences(content: string): string {
  return content
    .replace(/```[a-z]*\n?[\s\S]*?```/gi, (block) => (/\(\s*strategy/i.test(block) ? '' : block))
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

/* --------------------------------------------------------------- avatar ---- */
function Avatar({ user, initial }: { user?: boolean; initial?: string }) {
  return (
    <View
      style={{
        width: 32,
        height: 32,
        borderWidth: 2,
        borderColor: palette.ink,
        backgroundColor: user ? palette.orange[500] : palette.ink,
        alignItems: 'center',
        justifyContent: 'center',
      }}
    >
      {user ? (
        <Body size={13} color={palette.ink} style={{ fontFamily: fonts.display }}>
          {initial}
        </Body>
      ) : (
        <Sparkles color={palette.orange[500]} size={15} strokeWidth={2} />
      )}
    </View>
  );
}

/* ----------------------------------------------------------- caret / dots -- */
function Blink({ children }: { children: React.ReactNode }) {
  const v = useRef(new Animated.Value(1)).current;
  useEffect(() => {
    const a = Animated.loop(
      Animated.sequence([
        Animated.timing(v, { toValue: 0, duration: 500, useNativeDriver: true }),
        Animated.timing(v, { toValue: 1, duration: 500, useNativeDriver: true }),
      ]),
    );
    a.start();
    return () => a.stop();
  }, [v]);
  return <Animated.Text style={{ opacity: v, color: palette.orange[500], fontFamily: fonts.mono }}>{children}</Animated.Text>;
}

function Dot({ delay }: { delay: number }) {
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
        width: 7,
        height: 7,
        backgroundColor: palette.orange[500],
        transform: [{ translateY: v.interpolate({ inputRange: [0, 1], outputRange: [0, -5] }) }],
        opacity: v.interpolate({ inputRange: [0, 1], outputRange: [0.4, 1] }),
      }}
    />
  );
}

/* ---------------------------------------------------------------- bubbles -- */
function Bubble({ tone, label, children }: { tone: 'ink' | 'bone'; label: string; children: React.ReactNode }) {
  const me = tone === 'bone';
  const initial = useAuthStore((s) => (s.user?.firstName ?? s.user?.email ?? 'Y').charAt(0).toUpperCase());
  return (
    <View style={{ flexDirection: me ? 'row-reverse' : 'row', gap: 10, alignItems: 'flex-start' }}>
      <Avatar user={me} initial={initial} />
      <View style={{ flex: 1, alignItems: me ? 'flex-end' : 'flex-start', gap: 5 }}>
        <Mono size={8.5} color={palette.gray[500]} style={{ letterSpacing: 1 }}>
          {label}
        </Mono>
        <View
          style={[
            {
              maxWidth: '96%',
              borderWidth: 2,
              borderColor: me ? palette.orange[500] : palette.ink,
              backgroundColor: me ? palette.ink : palette.paper,
              paddingHorizontal: 12,
              paddingVertical: 9,
            },
            hardShadow(me ? palette.orange[500] : palette.ink),
          ]}
        >
          {children}
        </View>
      </View>
    </View>
  );
}

function ToolRow({ name, status }: { name: string; status: 'running' | 'complete' | 'error' }) {
  const spin = useRef(new Animated.Value(0)).current;
  useEffect(() => {
    if (status !== 'running') return;
    const a = Animated.loop(Animated.timing(spin, { toValue: 1, duration: 1400, easing: Easing.linear, useNativeDriver: true }));
    a.start();
    return () => a.stop();
  }, [spin, status]);
  const chip = status === 'error' ? 'red' : status === 'complete' ? 'green' : 'orange';
  return (
    <View style={{ flexDirection: 'row', gap: 42 }}>
      <View style={{ width: 32 }} />
      <View
        style={{
          flex: 1,
          flexDirection: 'row',
          alignItems: 'center',
          gap: 7,
          borderWidth: 1.5,
          borderStyle: 'dashed',
          borderColor: palette.ink,
          paddingHorizontal: 9,
          paddingVertical: 6,
        }}
      >
        <Animated.View style={{ transform: [{ rotate: spin.interpolate({ inputRange: [0, 1], outputRange: ['0deg', '360deg'] }) }] }}>
          <Settings color={palette.ink} size={12} strokeWidth={2} />
        </Animated.View>
        <Mono size={9.5} style={{ fontWeight: '700', flexShrink: 1 }} numberOfLines={1}>
          {name}
        </Mono>
        <View style={{ marginLeft: 'auto' }}>
          <Badge label={status === 'running' ? 'running…' : status} variant={chip} />
        </View>
      </View>
    </View>
  );
}

/* Indented row (aligned under the avatar column) for tool rows / artifacts. */
function Indented({ children }: { children: React.ReactNode }) {
  return (
    <View style={{ flexDirection: 'row', gap: 42 }}>
      <View style={{ width: 32 }} />
      <View style={{ flex: 1 }}>{children}</View>
    </View>
  );
}

/* ----------------------------------------------------------------- screen -- */
export default function CopilotScreen() {
  const {
    messages,
    pendingArtifacts,
    isStreaming,
    streamingContent,
    currentToolCall,
    artifactIdsForCurrent,
    suggestedPrompts,
    error,
    serviceUnavailable,
    startNewChat,
    loadSessions,
    sendMessage,
    getSuggestedPrompts,
    clearError,
  } = useAgentStore();

  const [draft, setDraft] = useState('');
  const [historyOpen, setHistoryOpen] = useState(false);
  const scrollRef = useRef<ScrollView>(null);

  useEffect(() => {
    void getSuggestedPrompts('copilot');
    void loadSessions();
  }, [getSuggestedPrompts, loadSessions]);

  const prompts = suggestedPrompts.length ? suggestedPrompts.slice(0, 4) : DEFAULT_PROMPTS;
  const artifactFor = (id: string) => pendingArtifacts.find((a) => a.id === id);

  const send = (text: string) => {
    const t = text.trim();
    if (!t || isStreaming) return;
    setDraft('');
    void sendMessage(t, 'copilot');
  };

  const empty = messages.length === 0 && !isStreaming;

  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: palette.bone }}>
      {/* App bar */}
      <View
        style={{
          height: 46,
          borderBottomWidth: 2,
          borderColor: palette.ink,
          backgroundColor: palette.paper,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingHorizontal: 12,
        }}
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 6 }}>
          <Sparkles color={palette.orange[500]} size={16} strokeWidth={2} />
          <Body size={16} style={{ fontFamily: fonts.display, textTransform: 'uppercase' }}>
            Copilot
          </Body>
        </View>
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8 }}>
          <Pressable onPress={() => setHistoryOpen(true)} hitSlop={6} style={{ width: 30, height: 30, borderWidth: 2, borderColor: palette.ink, alignItems: 'center', justifyContent: 'center' }}>
            <History color={palette.ink} size={15} strokeWidth={2} />
          </Pressable>
          <Pressable
            onPress={startNewChat}
            style={{ flexDirection: 'row', alignItems: 'center', gap: 3, borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.orange[500], paddingHorizontal: 8, height: 30 }}
          >
            <Plus color={palette.ink} size={12} strokeWidth={2.5} />
            <Mono size={9} style={{ fontWeight: '700' }}>
              NEW
            </Mono>
          </Pressable>
        </View>
      </View>

      <KeyboardAvoidingView style={{ flex: 1 }} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView
          ref={scrollRef}
          contentContainerStyle={{ padding: 12, gap: 14 }}
          onContentSizeChange={() => scrollRef.current?.scrollToEnd({ animated: true })}
          keyboardShouldPersistTaps="handled"
        >
          {serviceUnavailable ? (
            <View style={{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.bone2, padding: 10 }}>
              <Mono size={10} color={palette.gray[600]}>
                Copilot service offline — is the agent running?
              </Mono>
            </View>
          ) : null}

          {error ? (
            <Pressable onPress={clearError} style={{ borderWidth: 2, borderColor: palette.red[500], backgroundColor: palette.red[50], padding: 10 }}>
              <Mono size={10} color={palette.red[600]}>
                {error} · tap to dismiss
              </Mono>
            </Pressable>
          ) : null}

          {empty ? (
            <View style={{ gap: 11, marginTop: 8 }}>
              <View style={[{ borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.paper, padding: 16 }, hardShadow(palette.ink)]}>
                <Sparkles color={palette.orange[500]} size={24} strokeWidth={2} />
                <Body size={20} style={{ fontFamily: fonts.display, textTransform: 'uppercase', marginTop: 10 }}>
                  LlamaTrade Copilot
                </Body>
                <Markdown
                  tone="ink"
                  size={13}
                  content={'Describe, build, edit or explain a strategy. I write **real DSL** and run it on your paper account.'}
                />
              </View>
              {prompts.map((p) => (
                <Pressable
                  key={p}
                  onPress={() => send(p)}
                  style={{ borderWidth: 1.5, borderColor: palette.ink, backgroundColor: palette.paper, paddingHorizontal: 11, paddingVertical: 11, flexDirection: 'row', gap: 8, alignItems: 'center' }}
                >
                  <Mono size={13} color={palette.orange[500]} style={{ fontWeight: '700' }}>
                    ＋
                  </Mono>
                  <Body size={12.5} style={{ flexShrink: 1 }}>
                    {p}
                  </Body>
                </Pressable>
              ))}
            </View>
          ) : (
            <>
              {messages.map((m: ChatMessage) => (
                <View key={m.id} style={{ gap: 12 }}>
                  <Bubble tone={m.role === 'user' ? 'bone' : 'ink'} label={`${m.role === 'user' ? 'YOU' : 'COPILOT'} · ${fmtTime(m.timeMs)}`}>
                    <Markdown content={m.artifactIds.length ? stripStrategyFences(m.content) : m.content} tone={m.role === 'user' ? 'bone' : 'ink'} />
                  </Bubble>
                  {m.artifactIds.map((id) => {
                    const a = artifactFor(id);
                    return a ? (
                      <Indented key={id}>
                        <ArtifactCard artifact={a} />
                      </Indented>
                    ) : null;
                  })}
                </View>
              ))}

              {currentToolCall ? <ToolRow name={currentToolCall.name} status={currentToolCall.status} /> : null}

              {artifactIdsForCurrent.map((id) => {
                const a = artifactFor(id);
                return a ? (
                  <Indented key={`live-${id}`}>
                    <ArtifactCard artifact={a} />
                  </Indented>
                ) : null;
              })}

              {isStreaming ? (
                streamingContent ? (
                  <Bubble tone="ink" label="COPILOT">
                    <Markdown content={stripStrategyFences(streamingContent)} tone="ink" />
                    <Blink>▋</Blink>
                  </Bubble>
                ) : currentToolCall ? null : (
                  <Indented>
                    <View style={[{ alignSelf: 'flex-start', flexDirection: 'row', gap: 4, borderWidth: 2, borderColor: palette.ink, backgroundColor: palette.paper, paddingHorizontal: 11, paddingVertical: 11 }, hardShadow(palette.ink)]}>
                      <Dot delay={0} />
                      <Dot delay={150} />
                      <Dot delay={300} />
                    </View>
                  </Indented>
                )
              ) : null}
            </>
          )}
        </ScrollView>

        {/* Composer */}
        <View style={{ borderTopWidth: 2, borderColor: palette.ink, backgroundColor: palette.paper, padding: 8, flexDirection: 'row', gap: 8, alignItems: 'flex-end' }}>
          <TextInput
            value={draft}
            onChangeText={setDraft}
            placeholder={serviceUnavailable ? 'Copilot offline…' : 'Ask Copilot to build, edit, or explain…'}
            placeholderTextColor={palette.gray[400]}
            editable={!serviceUnavailable}
            multiline
            style={{
              flex: 1,
              maxHeight: 120,
              borderWidth: 2,
              borderColor: palette.ink,
              backgroundColor: palette.bone,
              fontFamily: fonts.mono,
              fontSize: 12,
              color: palette.ink,
              paddingHorizontal: 10,
              paddingVertical: 9,
            }}
          />
          <Pressable
            onPress={() => send(draft)}
            disabled={!draft.trim() || isStreaming || serviceUnavailable}
            style={{
              width: 40,
              height: 40,
              backgroundColor: !draft.trim() || isStreaming ? palette.orange[300] : palette.orange[500],
              borderWidth: 2,
              borderColor: palette.ink,
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            {isStreaming ? <ActivityIndicator size="small" color={palette.ink} /> : <ArrowUp color={palette.ink} size={18} strokeWidth={2.5} />}
          </Pressable>
        </View>
      </KeyboardAvoidingView>

      <HistorySheet visible={historyOpen} onClose={() => setHistoryOpen(false)} />
    </SafeAreaView>
  );
}
