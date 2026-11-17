/** Shared chrome for the sign-in and create-account screens. */
import type { ReactNode } from 'react';
import { KeyboardAvoidingView, Platform, ScrollView, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { makeStyles, space } from '../theme';
import { BackButton, Logo, Notice, Text, type BackLink } from '../ui';

export function AuthShell({
  title,
  subtitle,
  back,
  children,
}: {
  title: string;
  subtitle: string;
  back?: BackLink;
  children: ReactNode;
}) {
  const s = useStyles();
  return (
    <SafeAreaView style={s.safe}>
      <KeyboardAvoidingView style={s.flex} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <ScrollView contentContainerStyle={s.body} keyboardShouldPersistTaps="handled">
          {back ? <BackButton back={back} /> : <View style={s.brand}><Logo size={40} showText /></View>}
          <View style={s.heading}>
            <Text variant="title">{title}</Text>
            <Text variant="small" tone="fg2">{subtitle}</Text>
          </View>
          {children}
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

export function FormError({ message }: { message: string | null }) {
  return message ? <Notice title="That didn't work." detail={message} /> : null;
}

const useStyles = makeStyles((t) => ({
  safe: { flex: 1, backgroundColor: t.c.canvas },
  flex: { flex: 1 },
  body: { flexGrow: 1, paddingHorizontal: space.gutter, paddingTop: 24, paddingBottom: 24, gap: 14 },
  brand: { marginBottom: 18 },
  heading: { gap: 6, marginBottom: 4 },
}));
