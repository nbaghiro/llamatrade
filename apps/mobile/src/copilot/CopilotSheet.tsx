import { useAgentStore } from '@llamatrade/core/stores/agent';
import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { router } from 'expo-router';
import { Activity, ChevronDown, History, Maximize2, X } from 'lucide-react-native';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { Animated, Easing, Keyboard, PanResponder, Platform, Pressable, ScrollView, useWindowDimensions, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { makeStyles, radius, space, useTheme } from '../theme';
import { Text } from '../ui';
import { Composer, LimitPanel, useCopilotLimit } from './Composer';
import { settle, sheetGeometry, stopTop, type SheetStop } from './sheetModel';
import { sendToCopilot, takePendingQuestion, useCopilotUi } from './store';
import { QuestionList } from './SubjectParts';
import { Thread } from './Thread';
import { useCurrentSubject } from './useSubjects';

const GRAB_H = 64;

/**
 * Copilot as a half sheet over the screen you're on (copilot/phone B). The first state answers
 * in place (panel2 A); drag up for the full conversation with sources. Mounted once at the root.
 */
export function CopilotSheet() {
  const stop = useCopilotUi((st) => st.sheet);
  const [mounted, setMounted] = useState(stop !== 'closed');
  useEffect(() => {
    if (stop !== 'closed') setMounted(true);
  }, [stop]);
  const onGone = useCallback(() => setMounted(false), []);
  if (!mounted) return null;
  return <SheetBody stop={stop} onGone={onGone} />;
}

function useKeyboardHeight(): number {
  const [h, setH] = useState(0);
  useEffect(() => {
    const show = Keyboard.addListener(Platform.OS === 'ios' ? 'keyboardWillShow' : 'keyboardDidShow', (e) => setH(e.endCoordinates.height));
    const hide = Keyboard.addListener(Platform.OS === 'ios' ? 'keyboardWillHide' : 'keyboardDidHide', () => setH(0));
    return () => {
      show.remove();
      hide.remove();
    };
  }, []);
  return h;
}

function SheetBody({ stop, onGone }: { stop: SheetStop; onGone: () => void }) {
  const { c } = useTheme();
  const s = useStyles();
  const insets = useSafeAreaInsets();
  const { height } = useWindowDimensions();
  const g = useMemo(() => sheetGeometry(height, insets.top), [height, insets.top]);
  const top = useRef(new Animated.Value(g.windowHeight)).current;
  const at = useRef(g.windowHeight);
  const [rest, setRest] = useState<SheetStop>('half');
  const setSheet = useCopilotUi((st) => st.setSheet);
  const pending = useCopilotUi((st) => st.pending);
  const { subject } = useCurrentSubject();
  const context = useCopilotUi((st) => st.context);
  const dashboardLoaded = useDashboardStore((st) => st.loaded);
  const messages = useAgentStore((st) => st.messages);
  const isStreaming = useAgentStore((st) => st.isStreaming);
  const limit = useCopilotLimit();
  const keyboard = useKeyboardHeight();

  useEffect(() => {
    const to = stopTop(stop, g);
    Animated.timing(top, { toValue: to, duration: 280, easing: Easing.out(Easing.cubic), useNativeDriver: true }).start(({ finished }) => {
      if (!finished) return;
      at.current = to;
      if (stop === 'closed') onGone();
      else setRest(stop);
    });
  }, [stop, g, top, onGone]);

  const resolved = !context || context.kind === 'account' || subject.kind !== 'account' || dashboardLoaded;
  useEffect(() => {
    if (stop === 'closed' || !pending || !resolved) return;
    const q = takePendingQuestion();
    if (q) sendToCopilot(q, subject, 'copilot').catch(() => undefined);
  }, [stop, pending, resolved, subject]);

  const pan = useMemo(
    () =>
      PanResponder.create({
        onMoveShouldSetPanResponder: (_, gs) => Math.abs(gs.dy) > 6 && Math.abs(gs.dy) > Math.abs(gs.dx),
        onPanResponderMove: (_, gs) => top.setValue(Math.max(g.fullTop, at.current + gs.dy)),
        onPanResponderRelease: (_, gs) => {
          const next = settle(Math.max(g.fullTop, at.current + gs.dy), gs.vy, g);
          if (next === useCopilotUi.getState().sheet) {
            Animated.timing(top, { toValue: stopTop(next, g), duration: 200, useNativeDriver: true }).start();
          } else {
            setSheet(next);
          }
        },
      }),
    [g, top, setSheet],
  );

  const ask = (text: string) => {
    sendToCopilot(text, subject, 'copilot').catch(() => undefined);
  };
  const full = rest === 'full';
  const restTop = stopTop(rest, g);
  const offset = useMemo(() => Animated.add(top, -g.fullTop), [top, g.fullTop]);
  const visible = g.windowHeight - restTop;
  const empty = messages.length === 0 && !isStreaming;

  return (
    <View pointerEvents="box-none" style={s.layer}>
      {full ? <Pressable accessibilityLabel="Make Copilot smaller" style={s.scrim} onPress={() => setSheet('half')} /> : null}
      <Animated.View style={[s.sheet, { top: g.fullTop, height: g.windowHeight - g.fullTop, transform: [{ translateY: offset }] }]}>
        <View {...pan.panHandlers} style={s.grabZone}>
          <View style={s.grab} />
          {full ? (
            <View style={s.head}>
              <Pressable accessibilityLabel="Half height" hitSlop={10} onPress={() => setSheet('half')}>
                <ChevronDown color={c.fg} size={22} strokeWidth={1.7} />
              </Pressable>
              <Text variant="subhead" numberOfLines={1} style={s.headTitle}>{subject.kind === 'account' ? 'Copilot' : subject.name}</Text>
              <Pressable
                accessibilityLabel="Earlier conversations"
                hitSlop={10}
                onPress={() => {
                  setSheet('closed');
                  router.push('/copilot/history');
                }}
              >
                <History color={c.fg2} size={20} strokeWidth={1.6} />
              </Pressable>
            </View>
          ) : (
            <View style={s.head}>
              <View style={s.subject}>
                <Activity color={c.accent} size={13} strokeWidth={1.8} />
                <Text variant="small" numberOfLines={1} style={s.subjectText}>{subject.kind === 'account' ? 'Your account' : subject.name}</Text>
                <Pressable accessibilityLabel="Close Copilot" hitSlop={8} onPress={() => setSheet('closed')}>
                  <X color={c.fg3} size={14} strokeWidth={1.8} />
                </Pressable>
              </View>
              <View style={s.flex} />
              <Pressable accessibilityLabel="Full height" hitSlop={10} onPress={() => setSheet('full')}>
                <Maximize2 color={c.fg2} size={18} strokeWidth={1.6} />
              </Pressable>
            </View>
          )}
        </View>

        <View style={{ height: Math.max(120, visible - GRAB_H - keyboard) }}>
          <ScrollView style={s.flex} contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
            {empty ? <QuestionList subject={subject} onAsk={ask} title={subject.kind === 'account' ? 'Ask about your account' : `Ask about ${subject.name}`} /> : null}
            {!empty ? <Thread subject={subject} compact={!full} onAsk={ask} /> : null}
            {full && !empty ? (
              <Text
                variant="smallStrong"
                tone="accent"
                onPress={() => {
                  setSheet('closed');
                  router.navigate('/(tabs)/copilot');
                }}
              >
                Continue in Copilot
              </Text>
            ) : null}
            {limit ? <LimitPanel subject={subject} onRetry={ask} /> : null}
          </ScrollView>
          {limit ? null : (
            <View style={[s.composer, { paddingBottom: keyboard ? 10 : Math.max(insets.bottom, 10) }]}>
              <Composer subject={subject} onSend={ask} />
            </View>
          )}
        </View>
      </Animated.View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  layer: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0 },
  scrim: { position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, backgroundColor: t.c.scrim },
  sheet: {
    position: 'absolute',
    left: 0,
    right: 0,
    backgroundColor: t.c.canvas,
    borderTopLeftRadius: radius.sheet + 6,
    borderTopRightRadius: radius.sheet + 6,
    borderTopWidth: 1,
    borderColor: t.c.lineStrong,
    ...t.shadow.lg,
  },
  grabZone: { paddingTop: 8, paddingBottom: 6, height: GRAB_H },
  grab: { width: 38, height: 5, borderRadius: 3, backgroundColor: t.c.lineStrong, alignSelf: 'center', marginBottom: 10 },
  head: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingHorizontal: space.gutter },
  headTitle: { flex: 1, textAlign: 'center' },
  subject: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 7,
    maxWidth: '75%',
    height: 32,
    paddingHorizontal: 12,
    borderRadius: radius.pill,
    backgroundColor: t.c.accentSoft,
  },
  subjectText: { flexShrink: 1 },
  body: { paddingHorizontal: space.gutter, paddingTop: 6, paddingBottom: 16, gap: 16 },
  composer: { paddingHorizontal: 16, paddingTop: 8 },
}));
