import { router } from 'expo-router';
import { useState } from 'react';
import { View } from 'react-native';

import { HomePreview } from '../../src/account/HomePreview';
import { useAppearanceStore } from '../../src/stores/appearance';
import { makeStyles, useTheme, type ThemeMode } from '../../src/theme';
import { AppearancePicker, ModePicker } from '../../src/ui/AppearancePicker';
import { Card, Screen, SectionLabel, Segmented, Text } from '../../src/ui';

const back = { label: 'Account', onPress: () => (router.canGoBack() ? router.back() : router.replace('/account')) };

const PAIRS = [
  { key: 'dark', label: 'Dark pair' },
  { key: 'light', label: 'Light pair' },
] as const;

export default function AppearanceScreen() {
  const s = useStyles();
  const { mode: shown } = useTheme();
  const modePref = useAppearanceStore((st) => st.mode);
  const [editing, setEditing] = useState<ThemeMode>(shown);

  return (
    <Screen title="Appearance" back={back} art="bold" artSeed="account-appearance">
      <HomePreview mode={editing} />
      <Segmented options={PAIRS} value={editing} onChange={setEditing} fill />

      <Card>
        <AppearancePicker editing={editing} />
      </Card>

      <SectionLabel>Mode</SectionLabel>
      <View style={s.mode}>
        <ModePicker />
        <Text variant="caption" tone="fg3">
          {modePref === 'system'
            ? `Follows your phone, which is ${shown} right now. Each mode keeps its own surface and accent.`
            : `The app stays ${modePref}. Each mode keeps its own surface and accent.`}
        </Text>
      </View>
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  mode: { gap: 8 },
}));
