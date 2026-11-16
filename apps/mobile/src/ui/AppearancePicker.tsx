import { Pressable, View } from 'react-native';

import { useAppearanceStore } from '../stores/appearance';
import { accentsFor, makeStyles, useTheme, type ModePreference } from '../theme';
import { Segmented, type Segment } from './Segmented';
import { Text } from './Text';

const MODES: readonly Segment<ModePreference>[] = [
  { key: 'system', label: 'System' },
  { key: 'light', label: 'Light' },
  { key: 'dark', label: 'Dark' },
];

/** Mode, surface and accent, as in the web app's Settings, Appearance. */
export function AppearancePicker() {
  const { mode: shown } = useTheme();
  const s = useStyles();
  const mode = useAppearanceStore((st) => st.mode);
  const darkSurface = useAppearanceStore((st) => st.darkSurface);
  const lightSurface = useAppearanceStore((st) => st.lightSurface);
  const accentKey = useAppearanceStore((st) => (shown === 'dark' ? st.darkAccent : st.lightAccent));
  const setMode = useAppearanceStore((st) => st.setMode);
  const setDarkSurface = useAppearanceStore((st) => st.setDarkSurface);
  const setLightSurface = useAppearanceStore((st) => st.setLightSurface);
  const setAccent = useAppearanceStore((st) => st.setAccent);

  return (
    <View style={s.wrap}>
      <View style={s.row}>
        <Text variant="smallStrong">Mode</Text>
        <Segmented options={MODES} value={mode} onChange={setMode} />
        {mode === 'system' ? (
          <Text variant="caption" tone="fg3">Follows your device, which is {shown} right now.</Text>
        ) : null}
      </View>

      <View style={s.row}>
        <Text variant="smallStrong">{shown === 'dark' ? 'Dark surface' : 'Light surface'}</Text>
        {shown === 'dark' ? (
          <Segmented
            options={[
              { key: 'black', label: 'Black' },
              { key: 'slate', label: 'Slate' },
            ]}
            value={darkSurface}
            onChange={setDarkSurface}
          />
        ) : (
          <Segmented
            options={[
              { key: 'white', label: 'White' },
              { key: 'warm', label: 'Warm' },
            ]}
            value={lightSurface}
            onChange={setLightSurface}
          />
        )}
      </View>

      <View style={s.row}>
        <Text variant="smallStrong">Accent</Text>
        <View accessibilityRole="radiogroup" style={s.swatches}>
          {accentsFor(shown).map((a) => {
            const on = a.key === accentKey;
            return (
              <Pressable
                key={a.key}
                accessibilityRole="radio"
                accessibilityLabel={a.label}
                accessibilityState={{ checked: on }}
                onPress={() => setAccent(shown, a.key)}
                hitSlop={4}
                style={[s.ring, on ? s.ringOn : null]}
              >
                <View style={[s.swatch, { backgroundColor: a.swatch }]} />
              </Pressable>
            );
          })}
        </View>
        <Text variant="caption" tone="fg3">Used for actions and selection in {shown} mode.</Text>
      </View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { gap: 18 },
  row: { gap: 8 },
  swatches: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  ring: { width: 32, height: 32, borderRadius: 16, alignItems: 'center', justifyContent: 'center', borderWidth: 1.5, borderColor: 'transparent' },
  ringOn: { borderColor: t.c.fg2 },
  swatch: { width: 24, height: 24, borderRadius: 12, borderWidth: 1, borderColor: 'rgba(127,127,127,0.35)' },
}));
