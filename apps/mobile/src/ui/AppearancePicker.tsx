import { Pressable, View } from 'react-native';

import { useAppearanceStore } from '../stores/appearance';
import { accentsFor, makeStyles, type ModePreference, type ThemeMode } from '../theme';
import { Segmented, type Segment } from './Segmented';
import { Text } from './Text';

export const MODE_OPTIONS: readonly Segment<ModePreference>[] = [
  { key: 'light', label: 'Light' },
  { key: 'dark', label: 'Dark' },
  { key: 'system', label: 'System' },
];

/** Light, Dark or System for the whole app. */
export function ModePicker() {
  const mode = useAppearanceStore((st) => st.mode);
  const setMode = useAppearanceStore((st) => st.setMode);
  return <Segmented options={MODE_OPTIONS} value={mode} onChange={setMode} fill />;
}

/** The surface and accent for one mode, so each pair is chosen where it will be used. */
export function AppearancePicker({ editing }: { editing: ThemeMode }) {
  const s = useStyles();
  const darkSurface = useAppearanceStore((st) => st.darkSurface);
  const lightSurface = useAppearanceStore((st) => st.lightSurface);
  const accentKey = useAppearanceStore((st) => (editing === 'dark' ? st.darkAccent : st.lightAccent));
  const setDarkSurface = useAppearanceStore((st) => st.setDarkSurface);
  const setLightSurface = useAppearanceStore((st) => st.setLightSurface);
  const setAccent = useAppearanceStore((st) => st.setAccent);
  const accents = accentsFor(editing);
  const current = accents.find((a) => a.key === accentKey);

  return (
    <View style={s.wrap}>
      <View style={s.row}>
        <Text variant="label" tone="fg3">{editing === 'dark' ? 'Dark surface' : 'Light surface'}</Text>
        {editing === 'dark' ? (
          <Segmented options={[{ key: 'black', label: 'Black' }, { key: 'slate', label: 'Slate' }]} value={darkSurface} onChange={setDarkSurface} fill />
        ) : (
          <Segmented options={[{ key: 'white', label: 'White' }, { key: 'warm', label: 'Warm' }]} value={lightSurface} onChange={setLightSurface} fill />
        )}
      </View>

      <View style={s.row}>
        <Text variant="label" tone="fg3">
          Accent in {editing}{current ? ` · ${current.label}` : ''}
        </Text>
        <View accessibilityRole="radiogroup" style={s.swatches}>
          {accents.map((a) => {
            const on = a.key === accentKey;
            return (
              <Pressable
                key={a.key}
                accessibilityRole="radio"
                accessibilityLabel={a.label}
                accessibilityState={{ checked: on }}
                onPress={() => setAccent(editing, a.key)}
                hitSlop={4}
                style={[s.ring, on ? s.ringOn : null]}
              >
                <View style={[s.swatch, { backgroundColor: a.swatch }]} />
              </Pressable>
            );
          })}
        </View>
        <Text variant="caption" tone="fg3">Used for charts, the background art, actions and selection.</Text>
      </View>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { gap: 18 },
  row: { gap: 8 },
  swatches: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  ring: { width: 34, height: 34, borderRadius: 17, alignItems: 'center', justifyContent: 'center', borderWidth: 1.5, borderColor: 'transparent' },
  ringOn: { borderColor: t.c.fg2 },
  swatch: { width: 26, height: 26, borderRadius: 13, borderWidth: 1, borderColor: 'rgba(127,127,127,0.35)' },
}));
