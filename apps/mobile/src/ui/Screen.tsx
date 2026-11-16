import { ChevronLeft } from 'lucide-react-native';
import type { ReactNode } from 'react';
import { Pressable, RefreshControl, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { makeStyles, space, useTheme } from '../theme';
import { Text } from './Text';

export interface BackLink {
  label: string;
  onPress: () => void;
}

/** A back link in the accent, as on the design's pushed screens. */
export function BackButton({ back }: { back: BackLink }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <Pressable accessibilityRole="link" onPress={back.onPress} hitSlop={10} style={s.back}>
      <ChevronLeft color={c.accent} size={18} strokeWidth={1.8} />
      <Text variant="body" tone="accent">
        {back.label}
      </Text>
    </Pressable>
  );
}

/** Page header: optional back link and eyebrow, a large title and a right-hand slot. */
export function ScreenHeader({
  title,
  back,
  eyebrow,
  right,
}: {
  title: string;
  back?: BackLink;
  eyebrow?: ReactNode;
  right?: ReactNode;
}) {
  const s = useStyles();
  return (
    <View style={s.header}>
      {back ? <BackButton back={back} /> : null}
      {eyebrow ? typeof eyebrow === 'string' ? <Text variant="label" tone="fg3">{eyebrow}</Text> : eyebrow : null}
      <View style={s.titleRow}>
        <Text variant="title" style={s.title} numberOfLines={2}>
          {title}
        </Text>
        {right ?? null}
      </View>
    </View>
  );
}

/** Standard screen: canvas, header and a scrolling body with pull to refresh. */
export function Screen({
  title,
  back,
  eyebrow,
  right,
  refreshing,
  onRefresh,
  children,
}: {
  /** Omit for a screen that draws its own top row. */
  title?: string;
  back?: BackLink;
  eyebrow?: ReactNode;
  right?: ReactNode;
  refreshing?: boolean;
  onRefresh?: () => void;
  children: ReactNode;
}) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <SafeAreaView edges={['top']} style={s.safe}>
      <ScrollView
        contentContainerStyle={s.body}
        showsVerticalScrollIndicator={false}
        keyboardShouldPersistTaps="handled"
        refreshControl={
          onRefresh ? (
            <RefreshControl refreshing={refreshing ?? false} onRefresh={onRefresh} tintColor={c.fg3} />
          ) : undefined
        }
      >
        {title ? <ScreenHeader title={title} back={back} eyebrow={eyebrow} right={right} /> : null}
        {children}
      </ScrollView>
    </SafeAreaView>
  );
}

const useStyles = makeStyles((t) => ({
  safe: { flex: 1, backgroundColor: t.c.canvas },
  body: { paddingHorizontal: space.gutter, paddingTop: 10, paddingBottom: 32, gap: space.gap },
  header: { gap: 6, marginBottom: 2 },
  back: { flexDirection: 'row', alignItems: 'center', gap: 2, marginLeft: -4, marginBottom: 8, alignSelf: 'flex-start' },
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  title: { flexShrink: 1 },
}));
