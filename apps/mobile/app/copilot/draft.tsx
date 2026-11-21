import { parsePreview } from '@llamatrade/core/agent/artifact';
import { strategyStructure } from '@llamatrade/core/agent/structure';
import { MessageRole, useAgentStore, type AgentMessage } from '@llamatrade/core/stores/agent';
import { router } from 'expo-router';
import { CircleCheck, CircleDashed, ChevronLeft } from 'lucide-react-native';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useCopilotLimit } from '../../src/copilot/Composer';
import { draftBlocks, type DraftBlock } from '../../src/copilot/draftBlocks';
import {
  answersMessage,
  changedAnswers,
  DEFAULTS_MESSAGE,
  hideDraftBlock,
  parseDraftQuestions,
  presetPicks,
  stripDraftInstruction,
  type DraftAsk,
  type DraftPicks,
} from '../../src/copilot/draftQuestions';
import { Markdown } from '../../src/copilot/Markdown';
import { sendToCopilot, useCopilotUi } from '../../src/copilot/store';
import { Asked, stripStrategyFences } from '../../src/copilot/Thread';
import { useCurrentSubject } from '../../src/copilot/useSubjects';
import { makeStyles, radius, space, useTheme } from '../../src/theme';
import { Button, Canvas, Notice, Text } from '../../src/ui';

function latestAsk(messages: readonly AgentMessage[]): { ask: DraftAsk; id: string } | null {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role === MessageRole.USER) continue;
    const ask = parseDraftQuestions(m.content);
    if (ask) return { ask, id: m.id };
  }
  return null;
}

/** Questions first, then the draft (builder/draft2 B and copilot/draft2 C). */
export default function DraftScreen() {
  const { c } = useTheme();
  const s = useStyles();
  const { subject } = useCurrentSubject();
  const messages = useAgentStore((st) => st.messages);
  const artifacts = useAgentStore((st) => st.pendingArtifacts);
  const isStreaming = useAgentStore((st) => st.isStreaming);
  const streaming = useAgentStore((st) => st.streamingContent);
  const limit = useCopilotLimit();
  const [picks, setPicks] = useState<DraftPicks>({});
  const [open, setOpen] = useState(0);

  useEffect(() => useCopilotUi.getState().setSheet('closed'), []);

  const description = useMemo(() => {
    const first = messages.find((m) => m.role === MessageRole.USER);
    return first ? stripDraftInstruction(first.content) : '';
  }, [messages]);
  const asked = useMemo(() => latestAsk(messages), [messages]);
  const artifact = artifacts.length ? artifacts[artifacts.length - 1] : null;
  const questions = asked?.ask.questions ?? [];
  const chosen = { ...presetPicks(questions), ...picks };
  const answeredAfter = asked ? messages.findIndex((m) => m.id === asked.id) < messages.length - 1 : false;

  const send = (text: string) => sendToCopilot(text, subject, 'copilot').catch(() => undefined);
  const write = () => send(answersMessage(questions, chosen));
  const skip = () => send(DEFAULTS_MESSAGE);

  const showQuestions = !artifact && asked && !answeredAfter;
  const lastReply = [...messages].reverse().find((m) => m.role !== MessageRole.USER);

  return (
    <Canvas art="bold" artSeed="copilot-draft">
      <SafeAreaView edges={['top']} style={s.flex}>
        <View style={s.nav}>
          <Pressable accessibilityRole="link" onPress={() => router.back()} hitSlop={10} style={s.back}>
            <ChevronLeft color={c.accent} size={20} strokeWidth={1.8} />
            <Text variant="body" tone="accent">Back</Text>
          </Pressable>
          <Text variant="subhead">{artifact ? 'Draft from Copilot' : 'Copilot'}</Text>
          <View style={s.navRight}>
            {showQuestions && !isStreaming ? (
              <Text variant="body" tone="accent" onPress={skip}>Skip</Text>
            ) : null}
          </View>
        </View>

        <ScrollView contentContainerStyle={s.body}>
          {limit ? <Notice title="Copilot can't answer right now." detail="Your description is kept in the conversation. Try again from the Copilot tab." /> : null}
          {!description && !isStreaming ? (
            <View style={s.empty}>
              <Text variant="heading">No draft yet</Text>
              <Text variant="body" tone="fg2">
                Describe a strategy on the Copilot tab, for example "Hold the strongest of a few stock ETFs and move to bonds when the market looks overbought". Copilot asks about anything unclear before it writes the draft.
              </Text>
            </View>
          ) : null}

          {artifact ? (
            <DraftView artifactId={artifact.id} description={description} changed={changedAnswers(questions, chosen)} />
          ) : (
            <>
              {description ? <Asked text={description} /> : null}
              {showQuestions && asked ? (
                <>
                  {asked.ask.intro ? <Text variant="small" tone="fg2">{asked.ask.intro}</Text> : null}
                  {questions.map((q, i) => {
                    const expanded = open === i;
                    return (
                      <Pressable
                        key={q.id}
                        accessibilityRole="button"
                        accessibilityState={{ expanded }}
                        onPress={() => setOpen(i)}
                        style={[s.q, expanded ? s.qOpen : null]}
                      >
                        <View style={s.qHead}>
                          <View style={s.num}>
                            <Text variant="numSmall" tone="accent" style={s.numText}>{i + 1}</Text>
                          </View>
                          <Text variant="bodyStrong" style={s.flex}>{q.label}</Text>
                          {expanded ? null : <Text variant="numSmall" tone="fg3" numberOfLines={1} style={s.pick}>{chosen[q.id]}</Text>}
                        </View>
                        {expanded ? (
                          <View style={s.options}>
                            {q.help ? <Text variant="small" tone="fg3">{q.help}</Text> : null}
                            {q.options.map((o) => {
                              const on = chosen[q.id] === o;
                              return (
                                <Pressable
                                  key={o}
                                  accessibilityRole="radio"
                                  accessibilityState={{ selected: on }}
                                  onPress={() => {
                                    setPicks((p) => ({ ...p, [q.id]: o }));
                                    if (i < questions.length - 1) setOpen(i + 1);
                                  }}
                                  style={[s.option, on ? s.optionOn : null]}
                                >
                                  <Text variant="small" tone={on ? 'fg' : 'fg2'}>{o}</Text>
                                  {o === q.preset ? <Text variant="caption" tone="fg3">Copilot's pick</Text> : null}
                                </Pressable>
                              );
                            })}
                          </View>
                        ) : null}
                      </Pressable>
                    );
                  })}
                  <Button label="Write the draft" onPress={write} disabled={isStreaming || !!limit} />
                </>
              ) : null}
              {!showQuestions && lastReply && !isStreaming && answeredAfter ? (
                <Markdown content={stripStrategyFences(lastReply.content)} size={15} />
              ) : null}
              {isStreaming ? (
                <View style={s.writing}>
                  <CircleDashed color={c.fg3} size={16} strokeWidth={1.7} />
                  <Text variant="small" tone="fg3">{asked ? 'Writing the draft' : 'Reading your description'}</Text>
                </View>
              ) : null}
              {isStreaming && streaming && !asked ? <Text variant="small" tone="fg2">{hideDraftBlock(stripStrategyFences(streaming))}</Text> : null}
            </>
          )}
        </ScrollView>
      </SafeAreaView>
    </Canvas>
  );
}

function DraftView({ artifactId, description, changed }: { artifactId: string; description: string; changed: string[] }) {
  const { c } = useTheme();
  const s = useStyles();
  const artifact = useAgentStore((st) => st.pendingArtifacts.find((a) => a.id === artifactId));
  const messages = useAgentStore((st) => st.messages);
  const commit = useAgentStore((st) => st.commitArtifact);
  const [saving, setSaving] = useState(false);
  const { subject } = useCurrentSubject();

  const preview = useMemo(() => (artifact ? parsePreview(artifact) : null), [artifact]);
  const structure = useMemo(() => (preview?.dsl_code ? strategyStructure(preview.dsl_code) : null), [preview]);
  const blocks: DraftBlock[] = useMemo(
    () => (structure ? draftBlocks(structure.lines, structure, [description, ...changed]) : []),
    [structure, description, changed],
  );
  const checked = messages.some((m) => m.toolCalls.some((t) => t.name === 'validate_dsl' && t.success));
  if (!artifact) return null;
  const saved = artifact.isCommitted;
  const symbols = structure?.symbols.length ?? preview?.symbols?.length ?? 0;

  const save = async () => {
    if (saved || saving) return;
    setSaving(true);
    try {
      await commit(artifact.id);
    } finally {
      setSaving(false);
    }
  };
  const backtest = () => {
    sendToCopilot('Backtest this draft over the last five years against SPY.', subject, 'copilot').catch(() => undefined);
    router.push('/(tabs)/copilot');
  };

  const status = [checked ? 'Valid' : 'Not checked yet', symbols ? `${symbols} ${symbols === 1 ? 'symbol' : 'symbols'}` : '', saved ? 'saved as a draft' : 'not saved']
    .filter(Boolean)
    .join(' · ');

  return (
    <View style={s.draft}>
      <Text variant="heading">{artifact.name || structure?.name || 'Untitled draft'}</Text>
      <View style={s.statusRow}>
        {checked ? <CircleCheck color={c.accent} size={16} strokeWidth={1.7} /> : <CircleDashed color={c.fg3} size={16} strokeWidth={1.7} />}
        <Text variant="small" tone="fg3">{status}</Text>
      </View>
      {blocks.length ? (
        blocks.map((b, i) => (
          <View key={`${b.label}-${i}`} style={[s.block, b.author === 'copilot' ? s.blockCopilot : null]}>
            {b.author ? (
              <View style={[s.tag, b.author === 'copilot' ? s.tagCopilot : null]}>
                <Text variant="numSmall" tone={b.author === 'copilot' ? 'accent' : 'fg3'} style={s.tagText}>
                  {b.author === 'copilot' ? 'Copilot' : 'You'}
                </Text>
              </View>
            ) : null}
            <Text variant="label" tone="fg3" style={s.blockLabel}>{b.label.toUpperCase()}</Text>
            {b.value ? <Text variant="body">{b.value}</Text> : null}
          </View>
        ))
      ) : (
        <Text variant="small" tone="fg2">{artifact.description || 'Copilot wrote a draft, but its rules could not be read here. Save it and open it in the builder.'}</Text>
      )}
      <Text variant="small" tone="fg3">
        Dashed blocks hold values your description didn't name, so Copilot chose them. Ask Copilot to change any of them, or edit the draft once it's saved.
      </Text>
      <View style={s.actions}>
        {saved ? (
          <Button label="Open the draft" onPress={() => router.push(`/strategy/${artifact.committedResourceId}`)} style={s.flex} />
        ) : (
          <Button label="Save as draft" onPress={save} loading={saving} style={s.flex} />
        )}
        <Button label="Backtest" variant="secondary" onPress={backtest} style={s.flex} />
      </View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  nav: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 12, paddingVertical: 10 },
  back: { flexDirection: 'row', alignItems: 'center', gap: 2, width: 80 },
  navRight: { width: 80, alignItems: 'flex-end' },
  body: { paddingHorizontal: space.gutter, paddingTop: 8, paddingBottom: 40, gap: 14 },
  empty: { gap: 10, paddingTop: 40 },
  q: { backgroundColor: t.c.panel, borderWidth: 1, borderColor: t.c.line, borderRadius: radius.lg, padding: 16, gap: 12 },
  qOpen: { borderColor: t.c.accent },
  qHead: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  num: { width: 22, height: 22, borderRadius: 11, borderWidth: 1, borderColor: t.c.accent, backgroundColor: t.c.accentSoft, alignItems: 'center', justifyContent: 'center' },
  numText: { fontSize: 11, lineHeight: 14 },
  pick: { maxWidth: '45%' },
  options: { gap: 8 },
  option: { borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.pill, paddingHorizontal: 16, paddingVertical: 11, flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', gap: 8 },
  optionOn: { borderColor: t.c.accent, backgroundColor: t.c.accentSoft },
  writing: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  draft: { gap: 14 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: -6 },
  block: { backgroundColor: t.c.panel, borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.lg, paddingHorizontal: 16, paddingTop: 14, paddingBottom: 14, gap: 6, marginTop: 6 },
  blockCopilot: { borderStyle: 'dashed', borderColor: t.c.accent },
  blockLabel: { letterSpacing: 0.8 },
  tag: { position: 'absolute', top: -10, right: 12, backgroundColor: t.c.panel, borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.pill, paddingHorizontal: 8, height: 20, justifyContent: 'center' },
  tagCopilot: { borderColor: t.c.accent },
  tagText: { fontSize: 10.5, lineHeight: 13 },
  actions: { flexDirection: 'row', gap: 10 },
}));
