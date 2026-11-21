import { pct } from '@llamatrade/core/format';
import { StrategyStatus } from '@llamatrade/core/proto/strategy_pb';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { router, type Href } from 'expo-router';
import { Clock, FileText, Layers, Search as SearchIcon } from 'lucide-react-native';
import { useEffect, useMemo, useState, type ReactNode } from 'react';
import { Pressable, TextInput, View } from 'react-native';
import { create } from 'zustand';

import { openCopilot } from '../src/copilot/store';
import { useHomeData } from '../src/home/data';
import { isQuiet, plannedRebalances, sessionRows, type SessionRow } from '../src/home/model';
import { narrow, pushRecent, type SearchItem } from '../src/home/search';
import { dayLabel } from '../src/home/when';
import { fonts, makeStyles, radius, useTheme } from '../src/theme';
import { CopilotMark, Screen, Text, pnlTone } from '../src/ui';

interface Entry extends SearchItem {
  section: 'Sessions' | 'Strategies' | 'Pages';
  sub?: string;
  right?: ReactNode;
  icon: 'session' | 'strategy' | 'page';
  live?: boolean;
  dot?: 'running' | 'stopped' | 'risk';
  go: () => void;
}

/** Recently opened entries, kept on this phone for the app session. */
const useRecent = create<{ keys: string[]; add: (k: string) => void }>()((set) => ({
  keys: [],
  add: (k) => set((st) => ({ keys: pushRecent(st.keys, k) })),
}));

const PAGES: { key: string; title: string; href: Href; keywords?: string[] }[] = [
  { key: 'p-portfolio', title: 'Portfolio', href: '/portfolio', keywords: ['equity', 'accounts'] },
  { key: 'p-activity', title: 'Activity', href: '/portfolio/activity', keywords: ['fills', 'statement', 'transactions'] },
  { key: 'p-checks', title: 'Checks against Alpaca', href: '/portfolio/checks', keywords: ['reconciliation', 'ledger'] },
  { key: 'p-funds', title: 'Add paper funds', href: '/portfolio/add-funds', keywords: ['deposit', 'money'] },
  { key: 'p-markets', title: 'Markets', href: '/markets', keywords: ['prices', 'watchlist'] },
  { key: 'p-sessions', title: 'Sessions', href: '/sessions' },
  { key: 'p-strategies', title: 'Strategies', href: '/strategies' },
  { key: 'p-notifications', title: 'Notifications', href: '/notifications' },
  { key: 'p-account', title: 'Account', href: '/account', keywords: ['settings', 'broker', 'plan'] },
];

/** Search (shell/palette2 A): useful before typing, narrows as you type, and can send the text to Copilot. */
export default function SearchScreen() {
  const { c } = useTheme();
  const s = useStyles();
  const d = useHomeData();
  const strategies = useStrategiesStore((st) => st.strategies);
  const { keys: recent, add } = useRecent();
  const [query, setQuery] = useState('');

  useEffect(() => {
    if (useStrategiesStore.getState().strategies.length === 0) useStrategiesStore.getState().fetchStrategies();
  }, []);

  const rows = useMemo(() => sessionRows(d.sessions), [d.sessions]);
  const next = useMemo(() => plannedRebalances(d.sessions, d.fills, d.now, 7, 1)[0] ?? null, [d.sessions, d.fills, d.now]);
  const openRow = (r: SessionRow) => {
    if (r.sessionId) router.push({ pathname: '/sessions/[id]', params: { id: r.sessionId } });
    else router.push({ pathname: '/strategy/[id]', params: { id: r.strategyId } });
  };

  const entries: Entry[] = useMemo(() => {
    const inSession = new Set(rows.filter((r) => r.state !== 'stopped').map((r) => r.strategyId));
    const sessionEntries: Entry[] = rows.map((r) => ({
      key: `s-${r.id}`,
      title: r.title,
      keywords: [r.mode, r.state],
      section: 'Sessions',
      icon: 'session',
      live: r.mode === 'live',
      dot: r.state === 'frozen' || r.state === 'error' ? 'risk' : r.state === 'stopped' ? 'stopped' : 'running',
      sub: r.state === 'stopped' ? 'Stopped' : r.state === 'frozen' ? 'Frozen' : undefined,
      right:
        r.state === 'stopped' || r.dayReturnPct === null ? null : (
          <Text variant="numSmall" tone={isQuiet(r.dayReturnPct) ? 'fg2' : pnlTone(r.dayReturnPct)}>
            {pct(r.dayReturnPct)}
          </Text>
        ),
      go: () => openRow(r),
    }));
    const strategyEntries: Entry[] = strategies
      .filter((st) => !inSession.has(st.id))
      .map((st) => ({
        key: `t-${st.id}`,
        title: st.name,
        keywords: st.symbols,
        section: 'Strategies',
        icon: 'strategy',
        sub: st.status === StrategyStatus.DRAFT ? `Draft, v${st.version}` : `v${st.version}`,
        go: () => router.push({ pathname: '/strategy/[id]', params: { id: st.id } }),
      }));
    const pageEntries: Entry[] = PAGES.map((p) => ({
      key: p.key,
      title: p.title,
      keywords: p.keywords,
      section: 'Pages',
      icon: 'page',
      go: () => router.push(p.href),
    }));
    return [...sessionEntries, ...strategyEntries, ...pageEntries];
  }, [rows, strategies]);

  const typing = query.trim().length > 0;
  const found = typing ? narrow(entries, query) : [];
  const recentEntries = recent.map((k) => entries.find((e) => e.key === k)).filter((e): e is Entry => e !== undefined);
  const choose = (e: Entry) => {
    add(e.key);
    e.go();
  };
  const ask = () => {
    openCopilot({ kind: 'account', id: 'account' }, { question: query.trim() });
    router.back();
  };

  return (
    <Screen artSeed="shell-search-palette" art="bold">
      <View style={s.bar}>
        <View style={s.field}>
          <SearchIcon color={c.fg3} size={17} strokeWidth={1.8} />
          <TextInput
            autoFocus
            value={query}
            onChangeText={setQuery}
            placeholder="Search sessions, strategies and pages"
            placeholderTextColor={c.fg3}
            returnKeyType="search"
            onSubmitEditing={() => (found[0] ? choose(found[0]) : typing ? ask() : undefined)}
            style={s.input}
            accessibilityLabel="Search"
          />
        </View>
        <Text variant="body" tone="accent" onPress={() => (router.canGoBack() ? router.back() : router.replace('/'))}>
          Cancel
        </Text>
      </View>

      {typing ? (
        <>
          {(['Sessions', 'Strategies', 'Pages'] as const).map((section) => {
            const list = found.filter((e) => e.section === section);
            if (list.length === 0) return null;
            return (
              <Group key={section} title={section.toUpperCase()}>
                {list.map((e) => (
                  <EntryRow key={e.key} entry={e} onPress={() => choose(e)} />
                ))}
              </Group>
            );
          })}
          <Group title="COPILOT">
            <Row icon={<CopilotMark size={16} />} title={`Ask Copilot: “${query.trim()}”`} onPress={ask} />
          </Group>
        </>
      ) : (
        <>
          {next ? (
            <Group title="TODAY">
              <Row
                highlighted
                icon={<Clock color={c.accent} size={16} strokeWidth={1.8} />}
                title={`${next.name} rebalances ${dayLabel(next.day, d.now) === 'Today' ? 'today' : dayLabel(next.day, d.now)}`}
                right={
                  <Text variant="numSmall" tone="fg3">
                    {next.mode}
                  </Text>
                }
                onPress={() => {
                  const r = rows.find((x) => x.id === next.sessionId);
                  if (r) openRow(r);
                }}
              />
            </Group>
          ) : null}
          {rows.length ? (
            <Group title="SESSIONS">
              {entries
                .filter((e) => e.section === 'Sessions')
                .map((e) => (
                  <EntryRow key={e.key} entry={e} onPress={() => choose(e)} />
                ))}
            </Group>
          ) : null}
          {recentEntries.length ? (
            <Group title="RECENT">
              {recentEntries.map((e) => (
                <EntryRow key={e.key} entry={e} onPress={() => choose(e)} />
              ))}
            </Group>
          ) : null}
        </>
      )}
    </Screen>
  );
}

function Group({ title, children }: { title: string; children: ReactNode }) {
  const s = useStyles();
  return (
    <View style={s.group}>
      <Text variant="label" tone="fg3" style={s.groupTitle}>
        {title}
      </Text>
      {children}
    </View>
  );
}

function EntryRow({ entry, onPress }: { entry: Entry; onPress: () => void }) {
  const { c } = useTheme();
  const s = useStyles();
  const icon =
    entry.icon === 'session' ? (
      <View style={[s.dot, entry.dot === 'risk' ? s.dotRisk : entry.dot === 'stopped' ? s.dotStopped : null]} />
    ) : entry.icon === 'strategy' ? (
      <Layers color={c.fg3} size={16} strokeWidth={1.7} />
    ) : (
      <FileText color={c.fg3} size={16} strokeWidth={1.7} />
    );
  return (
    <Row
      icon={icon}
      title={entry.title}
      tag={entry.icon === 'session' ? (entry.live ? 'LIVE' : 'PAPER') : undefined}
      live={entry.live}
      sub={entry.sub}
      right={entry.right}
      onPress={onPress}
    />
  );
}

function Row({
  icon,
  title,
  tag,
  live,
  sub,
  right,
  highlighted = false,
  onPress,
}: {
  icon: ReactNode;
  title: string;
  tag?: string;
  live?: boolean;
  sub?: string;
  right?: ReactNode;
  highlighted?: boolean;
  onPress: () => void;
}) {
  const s = useStyles();
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={({ pressed }) => [s.row, highlighted ? s.rowOn : null, pressed ? s.pressed : null]}>
      <View style={s.icon}>{icon}</View>
      <Text variant="body" numberOfLines={1} style={s.title}>
        {title}
      </Text>
      {tag ? (
        <View style={[s.tag, live ? s.tagLive : null]}>
          <Text variant="numSmall" style={[s.tagText, live ? s.tagTextLive : null]}>
            {tag}
          </Text>
        </View>
      ) : null}
      <View style={s.flex} />
      {sub ? (
        <Text variant="small" tone="fg3">
          {sub}
        </Text>
      ) : null}
      {right}
    </Pressable>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  pressed: { opacity: 0.7 },
  bar: { flexDirection: 'row', alignItems: 'center', gap: 12, marginTop: 4 },
  field: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    height: 40,
    paddingHorizontal: 12,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: t.c.lineStrong,
    backgroundColor: t.c.panel,
  },
  input: { flex: 1, fontFamily: fonts.sans, fontSize: 15, color: t.c.fg, paddingVertical: 0 },
  group: { gap: 2 },
  groupTitle: { marginBottom: 4, marginTop: 6 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 10, paddingHorizontal: 8, borderRadius: radius.md },
  rowOn: { backgroundColor: t.c.sunk },
  icon: { width: 18, alignItems: 'center' },
  title: { flexShrink: 1 },
  dot: { width: 7, height: 7, borderRadius: 4, backgroundColor: t.c.accent },
  dotRisk: { backgroundColor: t.c.risk, borderRadius: 2 },
  dotStopped: { backgroundColor: t.c.fg3, borderRadius: 1.5 },
  tag: { borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.pill, paddingHorizontal: 6 },
  tagLive: { backgroundColor: t.c.fg, borderColor: t.c.fg },
  tagText: { fontSize: 9.5, lineHeight: 14, color: t.c.fg2, letterSpacing: 0.4 },
  tagTextLive: { color: t.c.canvas },
}));
