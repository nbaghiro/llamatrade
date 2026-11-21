import { agentClient, getTenantContext } from '@llamatrade/core/net';
import { MessageRole, useAgentStore, type AgentSession } from '@llamatrade/core/stores/agent';
import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { router } from 'expo-router';
import { Search } from 'lucide-react-native';
import { useEffect, useMemo, useRef, useState } from 'react';
import { Pressable, ScrollView, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { LineChart } from '../../src/charts/LineChart';
import { CopilotMark } from '../../src/ui';
import { excerpt, highlight, hitsLabel, searchConversation, type SearchableConversation, type SearchHit } from '../../src/copilot/historySearch';
import { useCopilotUi } from '../../src/copilot/store';
import { fonts, makeStyles, radius, space, useTheme } from '../../src/theme';
import { Canvas, Loading, Text } from '../../src/ui';

/** How many recent conversations the phone loads to search; the service can't search messages yet. */
const SEARCH_DEPTH = 20;
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function sessionMs(s: AgentSession): number {
  const v = s.lastActivityAt?.seconds ?? s.createdAt?.seconds;
  return v ? Number(v) * 1000 : 0;
}

function when(ms: number): string {
  if (!ms) return '';
  const d = new Date(ms);
  const now = new Date();
  return d.toDateString() === now.toDateString()
    ? `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    : `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

async function loadConversation(id: string, title: string): Promise<SearchableConversation | null> {
  const context = getTenantContext();
  if (!context) return null;
  const res = await agentClient.getSession({ context, sessionId: id, includeMessages: true, messageLimit: 200 });
  return {
    id,
    title,
    messages: res.messages.map((m) => ({ id: m.id, user: m.role === MessageRole.USER, content: m.content })),
  };
}

/** Earlier conversations, with search over what was said (history2 A). */
export default function HistoryScreen() {
  const { c, mode } = useTheme();
  const s = useStyles();
  const sessions = useAgentStore((st) => st.sessions);
  const loading = useAgentStore((st) => st.sessionsLoading);
  const sessionCurves = useDashboardStore((st) => st.strategies);
  const [query, setQuery] = useState('');
  const [loaded, setLoaded] = useState<Record<string, SearchableConversation>>({});
  const [searching, setSearching] = useState(false);
  const [failed, setFailed] = useState(false);
  const tried = useRef(new Set<string>());

  useEffect(() => useCopilotUi.getState().setSheet('closed'), []);

  const recent = useMemo(() => [...sessions].sort((a, b) => sessionMs(b) - sessionMs(a)), [sessions]);

  useEffect(() => {
    useAgentStore.getState().loadSessions().catch(() => undefined);
  }, []);

  const active = !!query.trim();
  useEffect(() => {
    if (!active) return;
    const missing = recent.slice(0, SEARCH_DEPTH).filter((r) => !tried.current.has(r.id));
    if (!missing.length) return;
    for (const m of missing) tried.current.add(m.id);
    let cancelled = false;
    let done = false;
    setSearching(true);
    Promise.allSettled(missing.map((m) => loadConversation(m.id, m.title))).then((results) => {
      if (cancelled) return;
      done = true;
      const next: Record<string, SearchableConversation> = {};
      let anyFailed = false;
      for (const r of results) {
        if (r.status === 'fulfilled' && r.value) next[r.value.id] = r.value;
        else if (r.status === 'rejected') anyFailed = true;
      }
      setLoaded((prev) => ({ ...prev, ...next }));
      setFailed(anyFailed);
      setSearching(false);
    });
    return () => {
      cancelled = true;
      if (!done) for (const m of missing) tried.current.delete(m.id);
    };
  }, [active, recent]);

  const hits = useMemo(() => {
    if (!query.trim()) return [];
    return recent
      .slice(0, SEARCH_DEPTH)
      .map((r) => {
        const convo = loaded[r.id] ?? { id: r.id, title: r.title, messages: [] };
        return searchConversation(convo, query);
      })
      .filter((h): h is SearchHit => h !== null);
  }, [query, recent, loaded]);

  const open = (id: string) => {
    useAgentStore.getState().selectSession(id).catch(() => undefined);
    router.navigate('/(tabs)/copilot');
  };

  const curveFor = (title: string) => {
    const t = title.toLowerCase();
    const match = sessionCurves.find((sc) => t.includes(sc.name.toLowerCase()));
    return match?.equity.map((p) => p.value) ?? null;
  };

  const thumb = (title: string) => {
    const curve = curveFor(title);
    return (
      <View style={s.thumb}>
        {curve && curve.length > 1 ? <View style={s.stretch}><LineChart values={curve} height={30} fill={false} strokeWidth={1.4} /></View> : <CopilotMark size={16} />}
      </View>
    );
  };

  const hasQuery = !!query.trim();
  const titleOf = (id: string) => recent.find((r) => r.id === id);

  return (
    <Canvas art="bold" artSeed="copilot-history">
      <SafeAreaView edges={['top']} style={s.flex}>
        <View style={s.searchRow}>
          <View style={s.search}>
            <Search color={c.fg3} size={17} strokeWidth={1.8} />
            <TextInput
              value={query}
              onChangeText={setQuery}
              placeholder="Search what was said"
              placeholderTextColor={c.fg3}
              autoFocus
              autoCorrect={false}
              keyboardAppearance={mode}
              selectionColor={c.accent}
              returnKeyType="search"
              style={s.input}
            />
          </View>
          <Text variant="body" tone="accent" onPress={() => router.back()}>Cancel</Text>
        </View>

        <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
          {hasQuery ? (
            <>
              <Text variant="small" tone="fg3">
                {searching ? `Searching your last ${Math.min(SEARCH_DEPTH, recent.length)} conversations` : hitsLabel(hits.length, query)}
                {failed ? '. Some conversations could not be loaded.' : ''}
              </Text>
              {hits.map((h, i) => {
                const convo = titleOf(h.sessionId);
                const text = h.text ? excerpt(h.text, query) : '';
                return (
                  <Pressable key={h.sessionId} accessibilityRole="button" onPress={() => open(h.sessionId)} style={[s.hit, i === 0 ? s.hitFirst : null]}>
                    {thumb(convo?.title ?? '')}
                    <View style={s.flex}>
                      <View style={s.hitHead}>
                        <Text variant="bodyStrong" numberOfLines={1} style={s.flex}>{convo?.title || 'Untitled'}</Text>
                        <Text variant="numSmall" tone="fg3">{convo ? when(sessionMs(convo)) : ''}</Text>
                      </View>
                      {text ? (
                        <Text variant="small" tone="fg2">
                          {highlight(text, query).map((p, j) =>
                            p.match ? (
                              <Text key={j} variant="small" style={s.mark}>{p.text}</Text>
                            ) : (
                              <Text key={j} variant="small" tone="fg2">{p.text}</Text>
                            ),
                          )}
                        </Text>
                      ) : (
                        <Text variant="small" tone="fg3">Matches the title</Text>
                      )}
                    </View>
                  </Pressable>
                );
              })}
            </>
          ) : loading && !recent.length ? (
            <Loading label="Loading conversations" />
          ) : recent.length === 0 ? (
            <Text variant="small" tone="fg3" style={s.center}>No conversations yet. Questions you ask Copilot are kept here.</Text>
          ) : (
            recent.map((r) => (
              <Pressable key={r.id} accessibilityRole="button" onPress={() => open(r.id)} style={s.hit}>
                {thumb(r.title)}
                <View style={s.flex}>
                  <View style={s.hitHead}>
                    <Text variant="bodyStrong" numberOfLines={1} style={s.flex}>{r.title || 'Untitled'}</Text>
                    <Text variant="numSmall" tone="fg3">{when(sessionMs(r))}</Text>
                  </View>
                  <Text variant="small" tone="fg3">{r.messageCount === 1 ? '1 message' : `${r.messageCount} messages`}</Text>
                </View>
              </Pressable>
            ))
          )}
        </ScrollView>
      </SafeAreaView>
    </Canvas>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  stretch: { alignSelf: 'stretch' },
  center: { textAlign: 'center', paddingVertical: 40 },
  searchRow: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingHorizontal: space.gutter, paddingTop: 10, paddingBottom: 8 },
  search: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    height: 44,
    paddingHorizontal: 14,
    borderRadius: 22,
    backgroundColor: t.c.panel,
    borderWidth: 1,
    borderColor: t.c.line,
  },
  input: { flex: 1, fontFamily: fonts.sans, fontSize: 16, color: t.c.fg },
  body: { paddingHorizontal: space.gutter, paddingTop: 6, paddingBottom: 40, gap: 6 },
  hit: { flexDirection: 'row', gap: 14, paddingVertical: 12, paddingHorizontal: 12, marginHorizontal: -12, borderRadius: radius.lg },
  hitFirst: { backgroundColor: t.c.panel, borderWidth: 1, borderColor: t.c.line },
  hitHead: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 2 },
  thumb: {
    width: 54,
    height: 40,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: t.c.line,
    backgroundColor: t.c.panel,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 5,
    overflow: 'hidden',
  },
  mark: { fontFamily: fonts.medium, color: t.c.fg, backgroundColor: t.c.accentSoft },
}));
