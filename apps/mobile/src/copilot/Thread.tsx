import { describeConfirmation } from '@llamatrade/core/agent/confirmation';
import { MessageRole, useAgentStore, type AgentMessage } from '@llamatrade/core/stores/agent';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { router, type Href } from 'expo-router';
import { Check, ChevronRight, Lock, X } from 'lucide-react-native';
import { useEffect, useMemo, useRef, useState } from 'react';
import { ActivityIndicator, Animated, Easing, Pressable, View } from 'react-native';

import { makeStyles, radius, useTheme } from '../theme';
import { Button, Text } from '../ui';
import { sourcesLabel, threadSources, type Source } from './citations';
import { hideDraftBlock, parseDraftQuestions, stripDraftInstruction } from './draftQuestions';
import { Markdown } from './Markdown';
import { followUps, type CopilotSubject } from './subjects';
import { ThinkingBlock } from './ThinkingBlock';

/** Drops the raw strategy code fence from prose; the draft screen shows the strategy instead. */
export function stripStrategyFences(content: string): string {
  return content
    .replace(/```[a-z]*\n?[\s\S]*?```/gi, (block) => (/\(\s*strategy/i.test(block) ? '' : block))
    .replace(/\n{3,}/g, '\n\n')
    .trim();
}

function readable(m: AgentMessage): string {
  if (m.role === MessageRole.USER) return stripDraftInstruction(m.content);
  const ask = parseDraftQuestions(m.content);
  return stripStrategyFences(ask ? ask.intro : m.content);
}

export function useThreadSources(messages: readonly AgentMessage[]): Source[] {
  return useMemo(
    () =>
      threadSources(
        messages.map((m) => ({
          id: m.id,
          user: m.role === MessageRole.USER,
          tools: m.toolCalls.map((t) => ({ name: t.name, success: t.success })),
        })),
      ),
    [messages],
  );
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
      style={{ width: 6, height: 6, borderRadius: 3, backgroundColor: c.fg3, opacity: v.interpolate({ inputRange: [0, 1], outputRange: [0.35, 1] }) }}
    />
  );
}

/** The person's question: an ink bubble on the right. */
export function Asked({ text }: { text: string }) {
  const s = useStyles();
  return (
    <View style={s.asked}>
      <Text variant="body" style={s.askedText}>{text}</Text>
    </View>
  );
}

/** Numbered sources under an answer, each opening the page that shows the record when there is one. */
export function SourceList({ sources, highlight }: { sources: readonly Source[]; highlight?: number | null }) {
  const { c } = useTheme();
  const s = useStyles();
  if (!sources.length) return null;
  return (
    <View style={s.sources}>
      {sources.map((src, i) => {
        const href = sourceHref(src.tool);
        return (
          <Pressable
            key={src.n}
            accessibilityRole={href ? 'link' : undefined}
            disabled={!href}
            onPress={href ? () => router.push(href) : undefined}
            style={[s.sourceRow, i < sources.length - 1 ? s.divider : null, highlight === src.n ? s.sourceOn : null]}
          >
            <View style={s.citeChip}>
              <Text variant="numSmall" tone="accent" style={s.citeText}>{src.n}</Text>
            </View>
            <Text variant="smallStrong" style={s.flex} numberOfLines={1}>{src.title}</Text>
            {src.ok ? null : <Text variant="caption" tone="risk">Failed</Text>}
            {href ? <ChevronRight color={c.fg3} size={14} strokeWidth={1.8} /> : null}
          </Pressable>
        );
      })}
    </View>
  );
}

function sourceHref(tool: string): Href | null {
  switch (tool) {
    case 'get_positions':
    case 'get_portfolio_summary':
    case 'get_portfolio_performance':
      return '/portfolio';
    case 'list_strategies':
      return '/(tabs)/strategies';
    default:
      return null;
  }
}

/** Copilot's proposals (confirm2 A): actions that don't trade are confirmed in one card; trading is yours. */
function ConfirmCard({ subject }: { subject: CopilotSubject | null }) {
  const { c } = useTheme();
  const s = useStyles();
  const pending = useAgentStore((st) => st.pendingConfirmation);
  const confirm = useAgentStore((st) => st.confirmToolCall);
  const strategies = useStrategiesStore((st) => st.strategies);
  const [ticked, setTicked] = useState(true);
  useEffect(() => setTicked(true), [pending?.confirmationId]);
  if (!pending) return null;
  const names = Object.fromEntries(strategies.map((st) => [st.id, st.name]));
  const view = describeConfirmation(pending.toolName, pending.argumentsJson, names);
  const detail = view.args.map((a) => `${a.label} ${a.value}`).join(' · ');
  return (
    <View style={s.turn}>
      <View style={s.confirm}>
        <Pressable
          accessibilityRole="checkbox"
          accessibilityState={{ checked: ticked }}
          onPress={() => setTicked((v) => !v)}
          style={s.confirmRow}
        >
          <View style={[s.box, ticked ? { backgroundColor: c.accentFill, borderColor: c.accentFill } : null]}>
            {ticked ? <Check color={c.accentInk} size={13} strokeWidth={2.4} /> : null}
          </View>
          <View style={s.flex}>
            <Text variant="bodyStrong">{view.title}</Text>
            {detail ? <Text variant="small" tone="fg3">{detail}</Text> : null}
            <Text variant="caption" tone="fg3">{view.effect}</Text>
          </View>
        </Pressable>
        <View style={s.confirmActions}>
          <Button label={ticked ? 'Confirm 1' : 'Confirm'} disabled={!ticked} onPress={() => confirm(true)} style={s.flex} />
          <Button label="Decline" variant="secondary" onPress={() => confirm(false)} />
        </View>
      </View>
      {subject?.kind === 'session' && subject.state !== 'stopped' ? <YouDoThis subject={subject} /> : null}
    </View>
  );
}

/** The dashed card for what Copilot can't do: changing what a session trades opens the session for you. */
function YouDoThis({ subject }: { subject: CopilotSubject }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <View style={s.dashed}>
      <View style={s.rowBetween}>
        <Text variant="smallStrong">Switch the session</Text>
        <View style={s.row}>
          <Lock color={c.fg3} size={12} strokeWidth={1.8} />
          <Text variant="caption" tone="fg3">You do this</Text>
        </View>
      </View>
      <Text variant="small" tone="fg2">
        Copilot can't change what {subject.name} trades. A new version only applies once you switch the session yourself.
      </Text>
      <Button label="Open the session" variant="secondary" size="sm" onPress={() => router.push(`/sessions/${subject.id}`)} style={s.selfStart} />
    </View>
  );
}

interface ThreadProps {
  subject: CopilotSubject | null;
  /** The half sheet: only the last exchange, the answer cut to three lines. */
  compact?: boolean;
  onAsk: (question: string) => void;
  /** Called with a citation number when a marker is tapped. */
  onCite?: (n: number) => void;
  citeOn?: number | null;
}

/** A conversation: questions, answers with numbered sources, drafts, proposals and the streaming turn. */
export function Thread({ subject, compact = false, onAsk, onCite, citeOn }: ThreadProps) {
  const s = useStyles();
  const { c } = useTheme();
  const messages = useAgentStore((st) => st.messages);
  const isStreaming = useAgentStore((st) => st.isStreaming);
  const streamingContent = useAgentStore((st) => st.streamingContent);
  const thinkingContent = useAgentStore((st) => st.thinkingContent);
  const currentToolCall = useAgentStore((st) => st.currentToolCall);
  const pendingIds = useAgentStore((st) => st.pendingArtifactIdsForCurrentMessage);
  const pendingConfirmation = useAgentStore((st) => st.pendingConfirmation);
  const sources = useThreadSources(messages);
  const [expanded, setExpanded] = useState<string | null>(null);

  const shown = compact ? lastExchange(messages) : messages;
  const asked = messages.filter((m) => m.role === MessageRole.USER).map((m) => stripDraftInstruction(m.content));
  const next = subject && !isStreaming ? followUps(subject, asked, 1) : [];

  return (
    <View style={s.thread}>
      {shown.map((m) => {
        if (m.role === MessageRole.USER) return <Asked key={m.id} text={stripDraftInstruction(m.content)} />;
        const own = sources.filter((src) => src.messageId === m.id);
        const ask = parseDraftQuestions(m.content);
        const hasDraft = m.inlineArtifactIds.length > 0;
        const open = !compact || expanded === m.id;
        return (
          <View key={m.id} style={s.turn}>
            {!compact && m.thinking ? <ThinkingBlock content={m.thinking} autoExpanded={false} /> : null}
            <Pressable disabled={!compact} onPress={() => setExpanded(open ? null : m.id)}>
              <View style={open ? null : s.clamp}>
                <Markdown content={readable(m)} size={15} onCite={onCite} />
              </View>
            </Pressable>
            {ask || hasDraft ? (
              <Pressable accessibilityRole="button" onPress={() => router.push('/copilot/draft')} style={s.draftLink}>
                <Text variant="smallStrong" style={s.flex}>
                  {hasDraft ? 'The draft is ready' : `${ask?.questions.length ?? 0} questions before the draft`}
                </Text>
                <Text variant="small" tone="accent">{hasDraft ? 'Open' : 'Answer'}</Text>
              </Pressable>
            ) : null}
            {compact ? (
              <View style={s.chips}>
                {own.length ? (
                  <Pressable onPress={() => setExpanded(open ? null : m.id)} style={s.chip}>
                    <Text variant="small" tone="fg2">{open ? 'Fewer lines' : sourcesLabel(own.length)}</Text>
                  </Pressable>
                ) : null}
                {next.map((q) => (
                  <Pressable key={q} onPress={() => onAsk(q)} style={s.chip}>
                    <Text variant="small" tone="fg2" numberOfLines={1}>{q}</Text>
                  </Pressable>
                ))}
              </View>
            ) : (
              <SourceList sources={own} highlight={citeOn} />
            )}
          </View>
        );
      })}

      {isStreaming && currentToolCall ? (
        <View style={s.row}>
          {currentToolCall.status === 'running' ? (
            <ActivityIndicator size="small" color={c.fg3} />
          ) : currentToolCall.status === 'complete' ? (
            <Check color={c.accent} size={13} strokeWidth={2} />
          ) : (
            <X color={c.risk} size={13} strokeWidth={2} />
          )}
          <Text variant="small" tone="fg3">Reading {currentToolCall.name.replace(/^(get|list)_/, '').replace(/_/g, ' ')}</Text>
        </View>
      ) : null}
      {isStreaming && thinkingContent && !compact ? (
        <ThinkingBlock content={thinkingContent} autoExpanded={streamingContent.length === 0} streaming />
      ) : null}
      {isStreaming ? (
        streamingContent ? (
          <Markdown content={stripStrategyFences(hideDraftBlock(streamingContent))} size={15} />
        ) : currentToolCall ? null : (
          <View style={s.typing}>
            <Dot delay={0} />
            <Dot delay={150} />
            <Dot delay={300} />
          </View>
        )
      ) : null}
      {isStreaming && pendingIds.length ? <Text variant="small" tone="fg3">Writing the draft</Text> : null}
      {!isStreaming && pendingConfirmation ? <ConfirmCard subject={subject} /> : null}
    </View>
  );
}

function lastExchange(messages: readonly AgentMessage[]): AgentMessage[] {
  for (let i = messages.length - 1; i >= 0; i--) {
    if (messages[i].role === MessageRole.USER) return messages.slice(i);
  }
  return messages.slice(-1);
}

const useStyles = makeStyles((t) => ({
  thread: { gap: 16 },
  turn: { gap: 10 },
  flex: { flex: 1 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  selfStart: { alignSelf: 'flex-start' },
  asked: {
    alignSelf: 'flex-end',
    maxWidth: '82%',
    backgroundColor: t.c.fg,
    borderRadius: radius.lg,
    borderBottomRightRadius: radius.xs,
    paddingHorizontal: 14,
    paddingVertical: 10,
  },
  askedText: { color: t.c.canvas },
  clamp: { maxHeight: 22 * 3, overflow: 'hidden' },
  sources: { backgroundColor: t.c.panel, borderWidth: 1, borderColor: t.c.line, borderRadius: radius.lg, paddingHorizontal: 14 },
  sourceRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10 },
  sourceOn: { backgroundColor: t.c.accentSoft, marginHorizontal: -14, paddingHorizontal: 14 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  citeChip: { minWidth: 20, height: 18, borderRadius: radius.xs, backgroundColor: t.c.accentSoft, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 4 },
  citeText: { fontSize: 11, lineHeight: 14 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: { borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.pill, paddingHorizontal: 12, paddingVertical: 6, maxWidth: '100%' },
  draftLink: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: t.c.panel,
    borderWidth: 1,
    borderColor: t.c.accent,
    borderRadius: radius.lg,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  typing: { flexDirection: 'row', gap: 5, paddingVertical: 8 },
  confirm: { backgroundColor: t.c.panel, borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.lg, padding: 14, gap: 14 },
  confirmRow: { flexDirection: 'row', gap: 12, alignItems: 'flex-start' },
  box: { width: 20, height: 20, borderRadius: radius.xs, borderWidth: 1.5, borderColor: t.c.lineStrong, alignItems: 'center', justifyContent: 'center', marginTop: 1 },
  confirmActions: { flexDirection: 'row', gap: 8 },
  dashed: { borderWidth: 1, borderStyle: 'dashed', borderColor: t.c.lineStrong, borderRadius: radius.lg, padding: 14, gap: 8, backgroundColor: t.c.canvas },
}));
