import { Tabs } from 'expo-router';
import { Home, LineChart, Sparkles, User, Wallet } from 'lucide-react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { fonts, palette } from '../../src/theme';

const ICON = 22;
const STROKE = 2;

export default function TabsLayout() {
  const insets = useSafeAreaInsets();
  const bottom = insets.bottom || 8;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: palette.ink,
        tabBarInactiveTintColor: palette.gray[500],
        tabBarStyle: {
          backgroundColor: palette.paper,
          borderTopWidth: 2,
          borderTopColor: palette.ink,
          height: 52 + bottom,
          paddingTop: 8,
          paddingBottom: bottom,
        },
        tabBarLabelStyle: {
          fontFamily: fonts.mono,
          fontSize: 9,
          letterSpacing: 0.5,
          textTransform: 'uppercase',
          marginTop: 3,
        },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Home', tabBarIcon: ({ color }) => <Home color={color} size={ICON} strokeWidth={STROKE} /> }} />
      <Tabs.Screen name="portfolio" options={{ title: 'Book', tabBarIcon: ({ color }) => <Wallet color={color} size={ICON} strokeWidth={STROKE} /> }} />
      <Tabs.Screen name="copilot" options={{ title: 'Copilot', tabBarIcon: ({ color }) => <Sparkles color={color} size={ICON} strokeWidth={STROKE} /> }} />
      <Tabs.Screen name="strategies" options={{ title: 'Strats', tabBarIcon: ({ color }) => <LineChart color={color} size={ICON} strokeWidth={STROKE} /> }} />
      <Tabs.Screen name="account" options={{ title: 'You', tabBarIcon: ({ color }) => <User color={color} size={ICON} strokeWidth={STROKE} /> }} />
    </Tabs>
  );
}
