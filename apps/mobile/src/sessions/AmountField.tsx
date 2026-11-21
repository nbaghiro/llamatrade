import { TextInput, View } from 'react-native';

import { fonts, makeStyles, radius, useTheme } from '../theme';
import { money } from '@llamatrade/core/format';
import { Text } from '../ui';

/** A large dollar input with the free cash it draws from on the right. */
export function AmountField({
  value,
  onChange,
  available,
  label,
  error,
}: {
  value: string;
  onChange: (v: string) => void;
  available: number | null;
  label: string;
  error?: string | null;
}) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <View style={s.wrap}>
      <View style={[s.box, { borderColor: error ? c.riskLine : c.accent }]}>
        <Text variant="numLarge" tone="fg3" style={s.dollar}>$</Text>
        <TextInput
          accessibilityLabel={label}
          value={value}
          onChangeText={onChange}
          keyboardType="decimal-pad"
          placeholder="0.00"
          placeholderTextColor={c.fg3}
          style={[s.input, { color: c.fg }]}
        />
        {available !== null ? <Text variant="small" tone="fg3">of {money(available, 2)}</Text> : null}
      </View>
      {error ? <Text variant="small" tone="risk">{error}</Text> : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  wrap: { gap: 6 },
  box: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderWidth: 1.5,
    borderRadius: radius.lg,
    paddingHorizontal: 14,
    height: 60,
    backgroundColor: t.c.panel,
  },
  dollar: { fontSize: 24 },
  input: { flex: 1, fontFamily: fonts.monoSemibold, fontSize: 26, letterSpacing: -0.6, paddingVertical: 0 },
}));
