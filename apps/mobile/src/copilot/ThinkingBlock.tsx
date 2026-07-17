import { Brain, ChevronDown, ChevronRight } from 'lucide-react-native';
import { useState } from 'react';
import { Pressable, View } from 'react-native';

import { palette } from '../theme';
import { Body, Mono } from '../ui';

/**
 * Collapsible reasoning block — the Copilot's curated <thinking> for a turn.
 * Auto-collapses once the answer starts (via `autoExpanded`), stays tappable
 * afterward, and renders nothing when there is no reasoning.
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
  const [override, setOverride] = useState<boolean | null>(null);

  const trimmed = content.trim();
  if (!trimmed) return null;

  const expanded = override ?? autoExpanded;
  const Chevron = expanded ? ChevronDown : ChevronRight;

  return (
    <View style={{ alignSelf: 'stretch', borderWidth: 2, borderColor: palette.gray[400], backgroundColor: palette.bone }}>
      <Pressable
        onPress={() => setOverride(!expanded)}
        style={{ flexDirection: 'row', alignItems: 'center', gap: 6, paddingHorizontal: 10, paddingVertical: 7 }}
      >
        <Chevron color={palette.gray[500]} size={13} strokeWidth={2} />
        <Brain color={palette.orange[500]} size={13} strokeWidth={2} />
        <Mono size={9} color={palette.gray[500]} style={{ fontWeight: '700', letterSpacing: 1 }}>
          {streaming && override === null ? 'THINKING…' : 'THINKING'}
        </Mono>
      </Pressable>

      {expanded ? (
        <View style={{ borderTopWidth: 2, borderColor: palette.gray[400], paddingHorizontal: 10, paddingVertical: 8 }}>
          <Body size={12} color={palette.gray[600]} style={{ fontStyle: 'italic', lineHeight: 18 }}>
            {trimmed}
          </Body>
        </View>
      ) : null}
    </View>
  );
}
