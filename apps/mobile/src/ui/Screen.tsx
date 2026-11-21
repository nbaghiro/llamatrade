import { ChevronLeft } from 'lucide-react-native';
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import { Animated, Pressable, RefreshControl, useWindowDimensions, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { makeStyles, space, useTheme } from '../theme';
import { HeaderActions } from '../shell/HeaderActions';
import { artHeight, boldArtHeight, CandleBackdrop, type ArtIntensity } from './CandleBackdrop';
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

const ScreenScroll = createContext<Animated.Value | null>(null);

/** The screen's vertical scroll offset, native-driven, for headers that shrink on scroll. */
export function useScreenScroll(): Animated.Value | null {
  return useContext(ScreenScroll);
}

/**
 * The canvas with the screen's candle art behind it, for screens that lay out their own body
 * (Copilot, sign-in). `Screen` uses it too.
 */
export function Canvas({
  art = 'full',
  artSeed,
  scrollY,
  children,
}: {
  art?: ArtIntensity;
  artSeed: string | number;
  /** When given, the art drifts up at a fraction of the scroll speed. */
  scrollY?: Animated.Value;
  children: ReactNode;
}) {
  const s = useStyles();
  const { height } = useWindowDimensions();
  const h = art === 'bold' ? boldArtHeight(height) : artHeight(height);
  const translateY = useMemo(
    () =>
      scrollY?.interpolate({
        inputRange: [0, h],
        outputRange: [0, -h * PARALLAX],
        extrapolateLeft: 'clamp',
        extrapolateRight: 'extend',
      }),
    [scrollY, h],
  );
  return (
    <View style={s.canvas}>
      {art !== 'off' ? (
        <Animated.View pointerEvents="none" style={[s.art, translateY ? { transform: [{ translateY }] } : null]}>
          <CandleBackdrop seed={artSeed} intensity={art} height={h} />
        </Animated.View>
      ) : null}
      {children}
    </View>
  );
}

const PARALLAX = 0.4;

/**
 * Standard screen: canvas and candle art, header and a scrolling body with pull to refresh.
 * Tab screens (`tab`) get the bell and avatar on the right of the header.
 */
export function Screen({
  title,
  back,
  eyebrow,
  right,
  tab = false,
  art = 'full',
  artSeed,
  parallax = true,
  refreshing,
  onRefresh,
  children,
}: {
  /** Omit for a screen that draws its own top row. */
  title?: string;
  back?: BackLink;
  eyebrow?: ReactNode;
  right?: ReactNode;
  /** A top-level tab: shows the bell and avatar unless `right` is given. */
  tab?: boolean;
  /** Candle art behind the top of the screen; 'soft' for dense pages. */
  art?: ArtIntensity;
  /** Defaults to the title, so each page keeps its own chart. */
  artSeed?: string | number;
  /** The art drifts up as the page scrolls, on the native driver. */
  parallax?: boolean;
  refreshing?: boolean;
  onRefresh?: () => void;
  children: ReactNode;
}) {
  const { c } = useTheme();
  const s = useStyles();
  const scrollY = useRef(new Animated.Value(0)).current;
  const onScroll = useMemo(
    () => Animated.event([{ nativeEvent: { contentOffset: { y: scrollY } } }], { useNativeDriver: true }),
    [scrollY],
  );
  const headerRight = right ?? (tab ? <HeaderActions /> : undefined);
  // Only a pull shows the spinner: background reloads toggling it leave iOS's inset stuck.
  const [pulled, setPulled] = useState(false);
  useEffect(() => {
    if (!refreshing) setPulled(false);
  }, [refreshing]);
  const pull = useCallback(() => {
    setPulled(true);
    onRefresh?.();
  }, [onRefresh]);
  return (
    <ScreenScroll.Provider value={scrollY}>
      <Canvas art={art} artSeed={artSeed ?? title ?? 'screen'} scrollY={parallax ? scrollY : undefined}>
        <SafeAreaView edges={['top']} style={s.safe}>
          <Animated.ScrollView
            contentContainerStyle={s.body}
            showsVerticalScrollIndicator={false}
            keyboardShouldPersistTaps="handled"
            onScroll={onScroll}
            scrollEventThrottle={16}
            refreshControl={
              onRefresh ? (
                <RefreshControl refreshing={pulled && (refreshing ?? false)} onRefresh={pull} tintColor={c.fg3} />
              ) : undefined
            }
          >
            {title ? <ScreenHeader title={title} back={back} eyebrow={eyebrow} right={headerRight} /> : null}
            {children}
          </Animated.ScrollView>
        </SafeAreaView>
      </Canvas>
    </ScreenScroll.Provider>
  );
}

const useStyles = makeStyles((t) => ({
  canvas: { flex: 1, backgroundColor: t.c.canvas },
  art: { position: 'absolute', top: 0, left: 0, right: 0 },
  safe: { flex: 1 },
  body: { paddingHorizontal: space.gutter, paddingTop: 10, paddingBottom: 32, gap: space.gap },
  header: { gap: 6, marginBottom: 2 },
  back: { flexDirection: 'row', alignItems: 'center', gap: 2, marginLeft: -4, marginBottom: 8, alignSelf: 'flex-start' },
  titleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 12 },
  title: { flexShrink: 1 },
}));
