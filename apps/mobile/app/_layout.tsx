import { useFonts } from 'expo-font';
import { Stack, useRouter, useSegments } from 'expo-router';
import { StatusBar } from 'expo-status-bar';
import * as SplashScreen from 'expo-splash-screen';
import { useEffect, useState } from 'react';
import { SafeAreaProvider } from 'react-native-safe-area-context';

import { CopilotSheet } from '../src/copilot/CopilotSheet';
import '../src/net/clients'; // side-effect: configure() the shared @llamatrade/core clients at startup
import { useAppearanceStore } from '../src/stores/appearance';
import { isTokenExpired, useAuthStore } from '../src/stores/auth';
import { useTheme } from '../src/theme';

SplashScreen.preventAutoHideAsync();

/**
 * Route guard. Waits for the (async, SecureStore-backed) auth store to rehydrate
 * before deciding — otherwise a cold start flashes /login for a logged-in user.
 * An expired access token drops the session rather than rendering empty screens.
 */
function useAuthRedirect(ready: boolean) {
  const segments = useSegments();
  const router = useRouter();
  const hasHydrated = useAuthStore((s) => s.hasHydrated);
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);
  const accessToken = useAuthStore((s) => s.accessToken);
  const refreshToken = useAuthStore((s) => s.refreshToken);
  const logout = useAuthStore((s) => s.logout);

  useEffect(() => {
    if (!ready || !hasHydrated) return;

    // An expired access token only drops the session when there's no refresh
    // token — otherwise the transport refreshes it on the first RPC.
    if (isAuthenticated && isTokenExpired(accessToken) && !refreshToken) {
      logout();
      return;
    }

    const onAuthScreen = segments[0] === 'login' || segments[0] === 'register';
    const onResetScreen = segments[0] === 'account' && segments[1] === 'reset';
    if (!isAuthenticated && !onAuthScreen && !onResetScreen) {
      router.replace('/login');
    } else if (isAuthenticated && onAuthScreen) {
      router.replace('/(tabs)');
    }
  }, [ready, hasHydrated, isAuthenticated, accessToken, refreshToken, segments, router, logout]);
}

export default function RootLayout() {
  const [loaded, error] = useFonts({
    'Geist-Regular': require('../assets/fonts/Geist-Regular.ttf'),
    'Geist-Medium': require('../assets/fonts/Geist-Medium.ttf'),
    'Geist-SemiBold': require('../assets/fonts/Geist-SemiBold.ttf'),
    'Geist-Bold': require('../assets/fonts/Geist-Bold.ttf'),
    'GeistMono-Regular': require('../assets/fonts/GeistMono-Regular.ttf'),
    'GeistMono-Medium': require('../assets/fonts/GeistMono-Medium.ttf'),
    'GeistMono-SemiBold': require('../assets/fonts/GeistMono-SemiBold.ttf'),
  });
  const hasHydrated = useAuthStore((s) => s.hasHydrated);
  const { c, mode } = useTheme();
  const [appearanceReady, setAppearanceReady] = useState(() => useAppearanceStore.persist.hasHydrated());
  useEffect(() => useAppearanceStore.persist.onFinishHydration(() => setAppearanceReady(true)), []);
  const ready = (loaded || !!error) && hasHydrated && appearanceReady;

  useAuthRedirect(ready);

  useEffect(() => {
    if (ready) SplashScreen.hideAsync();
  }, [ready]);

  if (!ready) return null;

  return (
    <SafeAreaProvider>
      <StatusBar style={mode === 'dark' ? 'light' : 'dark'} />
      <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: c.canvas } }}>
        <Stack.Screen name="login" />
        <Stack.Screen name="register" />
        <Stack.Screen name="(tabs)" />
        <Stack.Screen name="strategy/[id]" />
        <Stack.Screen name="portfolio/index" />
        <Stack.Screen name="account/index" />
        <Stack.Screen name="notifications" />
        <Stack.Screen name="account/connect-broker" />
        <Stack.Screen name="account/plans" />
        <Stack.Screen name="spike" options={{ presentation: 'modal' }} />
      </Stack>
      <CopilotSheet />
    </SafeAreaProvider>
  );
}
