import type { ReactNode } from 'react';
import { ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { palette } from '../theme';
import { Display } from './index';

/** Standard tab screen: bone canvas, ink-bordered app bar, scrolling body. */
export function Screen({ title, right, children }: { title: string; right?: ReactNode; children: ReactNode }) {
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
        <Display size={16}>{title}</Display>
        {right ?? null}
      </View>
      <ScrollView contentContainerStyle={{ padding: 12, gap: 11 }} showsVerticalScrollIndicator={false}>
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}
