import { type AgentSession, useAgentStore } from '@llamatrade/core/stores/agent';
import { Modal, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { makeStyles, radius, space } from '../theme';
import { Text } from '../ui';

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function sessionMs(s: AgentSession): number {
  const v = s.lastActivityAt?.seconds ?? s.createdAt?.seconds;
  return v ? Number(v) * 1000 : 0;
}

/** Clock time for today and yesterday, a date for anything older. */
function when(ms: number, today: boolean): string {
  if (!ms) return '';
  const d = new Date(ms);
  return today
    ? `${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
    : `${MONTHS[d.getMonth()]} ${d.getDate()}`;
}

interface Group {
  label: string;
  recent: boolean;
  items: AgentSession[];
}

function group(sessions: AgentSession[]): Group[] {
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startYesterday = startToday - 86_400_000;
  const groups: Group[] = [
    { label: 'Today', recent: true, items: [] },
    { label: 'Yesterday', recent: true, items: [] },
    { label: 'Earlier', recent: false, items: [] },
  ];
  for (const s of sessions) {
    const ms = sessionMs(s);
    groups[ms >= startToday ? 0 : ms >= startYesterday ? 1 : 2].items.push(s);
  }
  return groups.filter((g) => g.items.length > 0);
}

/** Bottom sheet listing past conversations, grouped by day. */
export function HistorySheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const s = useStyles();
  const insets = useSafeAreaInsets();
  const sessions = useAgentStore((st) => st.sessions);
  const currentId = useAgentStore((st) => st.currentSessionId);
  const selectSession = useAgentStore((st) => st.selectSession);
  const startNewChat = useAgentStore((st) => st.startNewChat);

  const groups = group([...sessions].sort((a, b) => sessionMs(b) - sessionMs(a)));

  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable accessibilityLabel="Close conversations" style={s.scrim} onPress={onClose} />
      <View style={[s.sheet, { paddingBottom: Math.max(insets.bottom, 16) }]}>
        <View style={s.grab} />
        <View style={s.head}>
          <Text variant="subhead">Conversations</Text>
          <Text
            variant="bodyStrong"
            tone="accent"
            onPress={() => {
              startNewChat();
              onClose();
            }}
          >
            New
          </Text>
        </View>
        <ScrollView contentContainerStyle={s.list}>
          {sessions.length === 0 ? (
            <Text variant="small" tone="fg3" style={s.empty}>No conversations yet.</Text>
          ) : (
            groups.map((g) => (
              <View key={g.label}>
                <Text variant="label" tone="fg3" style={s.groupLabel}>{g.label}</Text>
                {g.items.map((item, i) => {
                  const active = item.id === currentId;
                  return (
                    <Pressable
                      key={item.id}
                      accessibilityRole="button"
                      accessibilityState={{ selected: active }}
                      onPress={() => {
                        selectSession(item.id);
                        onClose();
                      }}
                      style={({ pressed }) => [s.row, i < g.items.length - 1 ? s.divider : null, pressed ? s.pressed : null]}
                    >
                      <Text variant={active ? 'bodyStrong' : 'body'} tone={active ? 'accent' : 'fg'} numberOfLines={1} style={s.title}>
                        {item.title || 'Untitled'}
                      </Text>
                      <Text variant="numSmall" tone="fg3">{when(sessionMs(item), g.recent)}</Text>
                    </Pressable>
                  );
                })}
              </View>
            ))
          )}
        </ScrollView>
      </View>
    </Modal>
  );
}

const useStyles = makeStyles((t) => ({
  scrim: { flex: 1, backgroundColor: t.c.scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    bottom: 0,
    maxHeight: '78%',
    backgroundColor: t.c.panel,
    borderTopLeftRadius: radius.sheet,
    borderTopRightRadius: radius.sheet,
    borderTopWidth: 1,
    borderColor: t.c.lineStrong,
    paddingTop: 8,
    ...t.shadow.lg,
  },
  grab: { width: 38, height: 5, borderRadius: 3, backgroundColor: t.c.lineStrong, alignSelf: 'center', marginBottom: 10 },
  head: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', paddingHorizontal: space.gutter, paddingBottom: 6 },
  list: { paddingHorizontal: space.gutter, paddingBottom: 8 },
  groupLabel: { marginTop: 12, marginBottom: 2 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 12 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  pressed: { opacity: 0.6 },
  title: { flex: 1 },
  empty: { textAlign: 'center', paddingVertical: 40 },
}));
