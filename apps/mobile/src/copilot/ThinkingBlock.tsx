import { ChevronDown, ChevronRight } from 'lucide-react-native';
import { useState } from 'react';
import { Pressable, View } from 'react-native';

import { makeStyles, radius, useTheme } from '../theme';
import { Text } from '../ui';

/**
 * Collapsible reasoning for one Copilot turn. Collapses once the answer starts
 * (via `autoExpanded`), stays tappable, and renders nothing without reasoning.
 */
export function ThinkingBlock({
  content,
  autoExpanded,
  streaming = false,
}: {
  content: string;
  autoExpanded: boolean;
  streaming?: boolean;
}) {
  const { c } = useTheme();
  const s = useStyles();
  const [override, setOverride] = useState<boolean | null>(null);

  const trimmed = content.trim();
  if (!trimmed) return null;

  const expanded = override ?? autoExpanded;
  const Chevron = expanded ? ChevronDown : ChevronRight;

  return (
    <View style={s.box}>
      <Pressable accessibilityRole="button" onPress={() => setOverride(!expanded)} style={s.head}>
        <Chevron color={c.fg3} size={14} strokeWidth={1.8} />
        <Text variant="label" tone="fg3">
          {streaming && override === null ? 'Thinking' : 'Reasoning'}
        </Text>
      </Pressable>
      {expanded ? (
        <View style={s.body}>
          <Text variant="small" tone="fg2">{trimmed}</Text>
        </View>
      ) : null}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  box: { alignSelf: 'stretch', borderRadius: radius.md, borderWidth: 1, borderColor: t.c.line },
  head: { flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 7 },
  body: { borderTopWidth: 1, borderColor: t.c.line, paddingHorizontal: 10, paddingVertical: 8 },
}));
