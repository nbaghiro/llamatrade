import { Tabs } from 'expo-router';
import { Home, LineChart, Sparkles, User, Wallet, type LucideIcon } from 'lucide-react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { fonts, useTheme } from '../../src/theme';

const ICON_SIZE = 22;
const STROKE = 1.6;

const TABS: ReadonlyArray<{ name: string; title: string; Icon: LucideIcon }> = [
  { name: 'index', title: 'Home', Icon: Home },
  { name: 'portfolio', title: 'Portfolio', Icon: Wallet },
  { name: 'strategies', title: 'Strategies', Icon: LineChart },
  { name: 'copilot', title: 'Copilot', Icon: Sparkles },
  { name: 'account', title: 'Account', Icon: User },
];

export default function TabsLayout() {
  const { c } = useTheme();
  const insets = useSafeAreaInsets();
  const bottom = Math.max(insets.bottom, 8);

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: c.canvas },
        tabBarActiveTintColor: c.accent,
        tabBarInactiveTintColor: c.fg3,
        tabBarStyle: {
          backgroundColor: c.panel,
          borderTopWidth: 1,
          borderTopColor: c.line,
          height: 56 + bottom,
          paddingTop: 8,
          paddingBottom: bottom,
        },
        tabBarLabelStyle: { fontFamily: fonts.medium, fontSize: 10.5, marginTop: 2 },
      }}
    >
      {TABS.map(({ name, title, Icon }) => (
        <Tabs.Screen
          key={name}
          name={name}
          options={{
            title,
            tabBarIcon: ({ color }) => <Icon color={color} size={ICON_SIZE} strokeWidth={STROKE} />,
          }}
        />
      ))}
    </Tabs>
  );
}
