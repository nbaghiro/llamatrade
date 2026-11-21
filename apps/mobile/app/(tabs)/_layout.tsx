import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { Tabs } from 'expo-router';
import { Activity, ChartCandlestick, ChartLine, House, type LucideIcon } from 'lucide-react-native';
import { useEffect, type ComponentType } from 'react';
import { StyleSheet, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { useSessionsAttention } from '../../src/shell/attention';
import { TABS, type TabKey } from '../../src/shell/tabs';
import { fonts, useTheme } from '../../src/theme';
import { CopilotMark, Text } from '../../src/ui';

const ICON_SIZE = 22;
const STROKE = 1.6;

type TabIcon = ComponentType<{ color: string; size: number; strokeWidth?: number }>;

function CopilotTabIcon({ color, size }: { color: string; size: number }) {
  return <CopilotMark color={color} size={size + 2} />;
}

const ICON: Record<TabKey, TabIcon | LucideIcon> = {
  index: House,
  markets: ChartCandlestick,
  sessions: Activity,
  strategies: ChartLine,
  copilot: CopilotTabIcon,
};

/** Five tabs with Markets second (phone-nav2 A); the selected tab is ink and bold, never accent. */
export default function TabsLayout() {
  const { c } = useTheme();
  const insets = useSafeAreaInsets();
  const bottom = Math.max(insets.bottom, 8);
  const attention = useSessionsAttention();

  useEffect(() => {
    useTradingStore.getState().loadBlotter().catch(() => undefined);
    useNotificationsStore.getState().fetchNotifications().catch(() => undefined);
  }, []);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: c.canvas },
        tabBarActiveTintColor: c.fg,
        tabBarInactiveTintColor: c.fg3,
        tabBarStyle: {
          backgroundColor: c.canvas,
          borderTopWidth: StyleSheet.hairlineWidth,
          borderTopColor: c.lineStrong,
          height: 56 + bottom,
          paddingTop: 8,
          paddingBottom: bottom,
        },
      }}
    >
      {TABS.map(({ name, title }) => {
        const Icon = ICON[name];
        const flagged = name === 'sessions' && attention.count > 0;
        return (
          <Tabs.Screen
            key={name}
            name={name}
            options={{
              title,
              tabBarAccessibilityLabel: name === 'sessions' ? attention.label : title,
              tabBarLabel: ({ focused }) => (
                <Text
                  variant="caption"
                  color={focused ? c.fg : c.fg3}
                  style={{ fontFamily: focused ? fonts.semibold : fonts.medium, fontSize: 10.5, marginTop: 2 }}
                >
                  {title}
                </Text>
              ),
              tabBarIcon: ({ focused }) => (
                <View>
                  <Icon color={focused ? c.fg : c.fg3} size={ICON_SIZE} strokeWidth={STROKE} />
                  {flagged ? (
                    <View
                      style={{
                        position: 'absolute',
                        top: -1,
                        right: -4,
                        width: 9,
                        height: 9,
                        borderRadius: 5,
                        backgroundColor: c.risk,
                        borderWidth: 2,
                        borderColor: c.canvas,
                      }}
                    />
                  ) : null}
                </View>
              ),
            }}
          />
        );
      })}
    </Tabs>
  );
}
