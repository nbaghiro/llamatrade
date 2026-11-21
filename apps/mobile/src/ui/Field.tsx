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
  error,
  help,
  textContentType,
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
  /** Says what to do; outlines the input in amber. */
  error?: string | null;
  /** A quiet line under the input when there is no error. */
  help?: string;
  textContentType?: 'emailAddress' | 'password' | 'newPassword' | 'oneTimeCode' | 'organizationName' | 'none';
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
        textContentType={textContentType}
        style={[s.input, mono ? s.mono : null, error ? s.inputError : null]}
      />
      {error ? (
        <Text variant="small" tone="risk">
          {error}
        </Text>
      ) : help ? (
        <Text variant="caption" tone="fg3">
          {help}
        </Text>
      ) : null}
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
  inputError: { borderColor: t.c.risk },
}));
