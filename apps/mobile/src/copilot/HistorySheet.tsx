import { StatusBar } from 'expo-status-bar';
import { Plus, X } from 'lucide-react-native';
import { Modal, Pressable, ScrollView, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AgentSessionStatus, type AgentSession, useAgentStore } from '@llamatrade/core/stores/agent';
import { fonts, palette } from '../theme';
import { Body, Display, Label, Mono } from '../ui';

function relTime(ms: number): string {
  const diff = Date.now() - ms;
  const m = Math.floor(diff / 60000);
  if (m < 1) return 'now';
  if (m < 60) return `${m}m`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h`;
  const d = Math.floor(h / 24);
  if (d < 7) return `${d}d`;
  return new Date(ms).toLocaleDateString('en-US', { month: 'short', day: 'numeric' }).toUpperCase();
}

function dotColor(status: AgentSessionStatus): string {
  if (status === AgentSessionStatus.ACTIVE) return palette.orange[500];
  if (status === AgentSessionStatus.COMPLETED) return palette.green[500];
  return palette.gray[400];
}

function sessionMs(s: AgentSession): number {
  const v = s.lastActivityAt?.seconds ?? s.createdAt?.seconds;
  return v ? Number(v) * 1000 : 0;
}

interface Group {
  label: string;
  items: AgentSession[];
}

function group(sessions: AgentSession[]): Group[] {
  const now = new Date();
  const startToday = new Date(now.getFullYear(), now.getMonth(), now.getDate()).getTime();
  const startYesterday = startToday - 86400000;
  const today: AgentSession[] = [];
  const yesterday: AgentSession[] = [];
  const earlier: AgentSession[] = [];
  for (const s of sessions) {
    const ms = sessionMs(s);
    if (ms >= startToday) today.push(s);
    else if (ms >= startYesterday) yesterday.push(s);
    else earlier.push(s);
  }
  return [
    { label: 'Today', items: today },
    { label: 'Yesterday', items: yesterday },
    { label: 'Earlier', items: earlier },
  ].filter((g) => g.items.length > 0);
}

export function HistorySheet({ visible, onClose }: { visible: boolean; onClose: () => void }) {
  const sessions = useAgentStore((s) => s.sessions);
  const currentId = useAgentStore((s) => s.currentSessionId);
  const selectSession = useAgentStore((s) => s.selectSession);
  const startNewChat = useAgentStore((s) => s.startNewChat);

  const insets = useSafeAreaInsets();
  const groups = group([...sessions].sort((a, b) => sessionMs(b) - sessionMs(a)));

  return (
    <Modal visible={visible} animationType="slide" presentationStyle="fullScreen" onRequestClose={onClose}>
      <View style={{ flex: 1, backgroundColor: palette.ink }}>
        {visible ? <StatusBar style="light" /> : null}
        {/* Header */}
        <View
          style={{
            paddingTop: insets.top,
            height: 48 + insets.top,
            backgroundColor: palette.ink,
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'space-between',
            paddingHorizontal: 14,
          }}
        >
          <Display size={16} color={palette.orange[500]}>
            Conversations
          </Display>
          <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
            <Pressable
              onPress={() => {
                startNewChat();
                onClose();
              }}
              style={{ flexDirection: 'row', alignItems: 'center', gap: 4, borderWidth: 2, borderColor: palette.bone, paddingHorizontal: 8, paddingVertical: 4 }}
            >
              <Plus color={palette.bone} size={12} strokeWidth={2.5} />
              <Mono size={9} color={palette.bone} style={{ fontWeight: '700' }}>
                NEW
              </Mono>
            </Pressable>
            <Pressable onPress={onClose} hitSlop={8}>
              <X color={palette.bone} size={20} strokeWidth={2.5} />
            </Pressable>
          </View>
        </View>

        <ScrollView style={{ flex: 1, backgroundColor: palette.bone }} contentContainerStyle={{ padding: 12, paddingBottom: 40, gap: 8 }}>
          {sessions.length === 0 ? (
            <View style={{ paddingVertical: 40, alignItems: 'center' }}>
              <Label>No conversations yet</Label>
            </View>
          ) : (
            groups.map((g) => (
              <View key={g.label} style={{ gap: 8 }}>
                <Mono size={9} color={palette.gray[500]} style={{ letterSpacing: 1.2, marginTop: 6 }}>
                  {g.label.toUpperCase()}
                </Mono>
                {g.items.map((s) => {
                  const active = s.id === currentId;
                  return (
                    <Pressable
                      key={s.id}
                      onPress={() => {
                        void selectSession(s.id);
                        onClose();
                      }}
                      style={{
                        borderWidth: 2,
                        borderColor: palette.ink,
                        backgroundColor: palette.paper,
                        paddingHorizontal: 11,
                        paddingVertical: 10,
                        flexDirection: 'row',
                        alignItems: 'center',
                        gap: 9,
                        ...(active ? { borderLeftWidth: 5, borderLeftColor: palette.orange[500] } : {}),
                      }}
                    >
                      <View style={{ width: 7, height: 7, borderRadius: 0, backgroundColor: dotColor(s.status) }} />
                      <View style={{ flex: 1 }}>
                        <Body size={13} style={{ fontWeight: '700' }} numberOfLines={1}>
                          {s.title || 'Untitled'}
                        </Body>
                        <Mono size={9} color={palette.gray[500]} style={{ marginTop: 2 }}>
                          {s.messageCount} msgs · {relTime(sessionMs(s))}
                        </Mono>
                      </View>
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
