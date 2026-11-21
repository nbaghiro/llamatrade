import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { WifiOff } from 'lucide-react-native';
import { View } from 'react-native';

import { makeStyles, radius, useTheme } from '../theme';
import { Text } from '../ui/Text';
import { figuresTime, isNetworkError } from './offline';

/**
 * A grey strip when the app can't reach LlamaTrade (offline2 B): trading continues on the
 * servers, and the figures shown are from the time given. Reads the dashboard's last error
 * unless `error` is passed, so any screen can mount it.
 */
export function OfflineStrip({ error, asOf }: { error?: string | null; asOf?: Date | null }) {
  const { c } = useTheme();
  const s = useStyles();
  const dashError = useDashboardStore((st) => st.error);
  const dashAsOf = useDashboardStore((st) => st.equityAsOf);
  const message = error === undefined ? dashError : error;
  if (!isNetworkError(message)) return null;
  const time = figuresTime(asOf === undefined ? dashAsOf : asOf, new Date());
  return (
    <View style={s.strip} accessibilityRole="alert">
      <WifiOff color={c.fg2} size={15} strokeWidth={1.8} style={s.icon} />
      <Text variant="small" tone="fg2" style={s.text}>
        <Text variant="smallStrong">You're offline. </Text>
        Your sessions keep trading on LlamaTrade's servers.{time ? ` Figures from ${time}.` : ''}
      </Text>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  strip: {
    flexDirection: 'row',
    gap: 9,
    paddingHorizontal: 12,
    paddingVertical: 10,
    borderRadius: radius.md,
    backgroundColor: t.c.sunk,
    borderWidth: 1,
    borderColor: t.c.line,
  },
  icon: { marginTop: 2 },
  text: { flex: 1 },
}));
