import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { router } from 'expo-router';
import { Bell } from 'lucide-react-native';
import { Pressable, View } from 'react-native';

import { useAuthStore } from '../stores/auth';
import { fonts, makeStyles, useTheme } from '../theme';
import { Text } from '../ui/Text';
import { initials } from './tabs';

/** The bell (notifications) and the avatar (Account), on the right of every tab's header. */
export function HeaderActions() {
  const { c } = useTheme();
  const s = useStyles();
  const unread = useNotificationsStore((st) => st.unreadCount);
  const user = useAuthStore((st) => st.user);
  return (
    <View style={s.row}>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel={unread > 0 ? `Notifications, ${unread} unread` : 'Notifications'}
        onPress={() => router.push('/notifications')}
        hitSlop={8}
        style={s.icon}
      >
        <Bell color={c.fg2} size={21} strokeWidth={1.6} />
        {unread > 0 ? <View style={s.dot} /> : null}
      </Pressable>
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Account"
        onPress={() => router.push('/account')}
        hitSlop={6}
        style={s.avatar}
      >
        <Text variant="label" style={s.avatarText}>
          {initials(user)}
        </Text>
      </Pressable>
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  icon: { width: 34, height: 34, alignItems: 'center', justifyContent: 'center' },
  dot: {
    position: 'absolute',
    top: 6,
    right: 6,
    width: 8,
    height: 8,
    borderRadius: 4,
    backgroundColor: t.c.accent,
    borderWidth: 1.5,
    borderColor: t.c.canvas,
  },
  avatar: {
    width: 32,
    height: 32,
    borderRadius: 16,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: t.c.sunk,
    borderWidth: 1,
    borderColor: t.c.lineStrong,
  },
  avatarText: { fontFamily: fonts.semibold, fontSize: 12, color: t.c.fg2 },
}));
