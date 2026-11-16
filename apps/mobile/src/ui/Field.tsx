import { TextInput, View, type KeyboardTypeOptions } from 'react-native';

import { fonts, makeStyles, radius, useTheme } from '../theme';
import { Text } from './Text';

export function Field({
  label,
  value,
  onChange,
  placeholder,
  secure = false,
  autoCapitalizeWords = false,
  keyboardType,
  mono = false,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  secure?: boolean;
  autoCapitalizeWords?: boolean;
  keyboardType?: KeyboardTypeOptions;
  /** Mono face for keys and codes. */
  mono?: boolean;
}) {
  const { c, mode } = useTheme();
  const s = useStyles();
  return (
    <View style={s.wrap}>
      <Text variant="label" tone="fg2">
        {label}
      </Text>
      <TextInput
        accessibilityLabel={label}
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={c.fg3}
        autoCapitalize={autoCapitalizeWords ? 'words' : 'none'}
        autoCorrect={false}
        keyboardType={keyboardType ?? 'default'}
        secureTextEntry={secure}
        keyboardAppearance={mode}
        selectionColor={c.accent}
        style={[s.input, mono ? s.mono : null]}
      />
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { gap: 6 },
  input: {
    height: 46,
    borderRadius: radius.md,
    borderWidth: 1,
    borderColor: t.c.lineStrong,
    backgroundColor: t.c.panel,
    paddingHorizontal: 12,
    fontFamily: fonts.sans,
    fontSize: 15,
    color: t.c.fg,
  },
  mono: { fontFamily: fonts.mono, fontSize: 14 },
}));
