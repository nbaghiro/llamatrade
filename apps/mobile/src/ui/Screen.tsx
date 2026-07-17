import { ChevronLeft } from 'lucide-react-native';
import type { ReactNode } from 'react';
import { Pressable, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { palette } from '../theme';
import { Display } from './index';

/** Standard screen: bone canvas, ink-bordered app bar (optional back), scrolling body. */
export function Screen({
  title,
  right,
  onBack,
  children,
}: {
  title: string;
  right?: ReactNode;
  onBack?: () => void;
  children: ReactNode;
}) {
  return (
    <SafeAreaView edges={['top']} style={{ flex: 1, backgroundColor: palette.bone }}>
      <View
        style={{
          height: 46,
          borderBottomWidth: 2,
          borderColor: palette.ink,
          backgroundColor: palette.paper,
          flexDirection: 'row',
          alignItems: 'center',
          justifyContent: 'space-between',
          paddingHorizontal: 14,
        }}
      >
        <View style={{ flexDirection: 'row', alignItems: 'center', gap: 8, flex: 1 }}>
          {onBack ? (
            <Pressable onPress={onBack} hitSlop={10}>
              <ChevronLeft color={palette.ink} size={22} strokeWidth={2.5} />
            </Pressable>
          ) : null}
          <Display size={16}>{title}</Display>
        </View>
        {right ?? null}
      </View>
      <ScrollView contentContainerStyle={{ padding: 12, gap: 11 }} showsVerticalScrollIndicator={false}>
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}
