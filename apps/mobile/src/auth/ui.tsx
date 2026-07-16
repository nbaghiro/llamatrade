/** Shared chrome for the sign-in / sign-up screens. */
import { useState } from 'react';
import { Pressable, TextInput, View } from 'react-native';
import Svg, { Path, Rect } from 'react-native-svg';

import { fonts, palette } from '../theme';
import { Display, Label, Mono } from '../ui';
import { Logo } from '../ui/Logo';

export function AuthBrand() {
  return (
    <View style={{ alignItems: 'center', gap: 8, marginBottom: 6 }}>
      <Logo size={52} />
      <Display size={26}>LlamaTrade</Display>
      <Label>Algorithmic Trading</Label>
      <View style={{ width: 44, height: 4, backgroundColor: palette.orange[500] }} />
    </View>
  );
}

export function Field({
  label,
  value,
  onChange,
  placeholder,
  secure,
  autoCapitalizeWords,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder: string;
  secure?: boolean;
  autoCapitalizeWords?: boolean;
}) {
  return (
    <View>
      <Label style={{ marginBottom: 5 }}>{label}</Label>
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={palette.gray[400]}
        autoCapitalize={autoCapitalizeWords ? 'words' : 'none'}
        autoCorrect={false}
        keyboardType={secure || autoCapitalizeWords ? 'default' : 'email-address'}
        secureTextEntry={secure}
        style={{
          borderWidth: 2,
          borderColor: palette.ink,
          backgroundColor: palette.paper,
          fontFamily: fonts.mono,
          fontSize: 13,
          color: palette.ink,
          paddingHorizontal: 11,
          paddingVertical: 11,
        }}
      />
    </View>
  );
}

function GoogleMark() {
  return (
    <Svg width={16} height={16} viewBox="0 0 18 18">
      <Path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.71-1.57 2.68-3.88 2.68-6.62Z" />
      <Path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z" />
      <Path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33Z" />
      <Path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z" />
    </Svg>
  );
}

function MicrosoftMark() {
  return (
    <Svg width={15} height={15} viewBox="0 0 20 20">
      <Rect x={1} y={1} width={8} height={8} fill="#F25022" />
      <Rect x={11} y={1} width={8} height={8} fill="#7FBA00" />
      <Rect x={1} y={11} width={8} height={8} fill="#00A4EF" />
      <Rect x={11} y={11} width={8} height={8} fill="#FFB900" />
    </Svg>
  );
}

function SocialButton({ mark, label, onPress }: { mark: React.ReactNode; label: string; onPress: () => void }) {
  return (
    <Pressable
      onPress={onPress}
      style={{
        borderWidth: 2,
        borderColor: palette.ink,
        backgroundColor: palette.paper,
        paddingVertical: 12,
        flexDirection: 'row',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 9,
      }}
    >
      {mark}
      <Mono size={12} style={{ fontWeight: '700' }}>{label}</Mono>
    </Pressable>
  );
}

/**
 * "Or continue with" social buttons. Presentational until OAuth is wired — real
 * handlers can be injected via `onGoogle`/`onMicrosoft`; otherwise tapping shows
 * an honest "coming soon" note rather than a dead button.
 */
export function SocialAuth({ onGoogle, onMicrosoft }: { onGoogle?: () => void; onMicrosoft?: () => void }) {
  const [note, setNote] = useState(false);
  const google = onGoogle ?? (() => setNote(true));
  const microsoft = onMicrosoft ?? (() => setNote(true));

  return (
    <View style={{ marginTop: 4, gap: 12 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 10 }}>
        <View style={{ flex: 1, height: 1, backgroundColor: 'rgba(13,13,13,0.15)' }} />
        <Mono size={9} color={palette.gray[500]} style={{ letterSpacing: 2, fontWeight: '700' }}>OR</Mono>
        <View style={{ flex: 1, height: 1, backgroundColor: 'rgba(13,13,13,0.15)' }} />
      </View>
      <SocialButton mark={<GoogleMark />} label="Continue with Google" onPress={google} />
      <SocialButton mark={<MicrosoftMark />} label="Continue with Microsoft" onPress={microsoft} />
      {note ? (
        <Mono size={9} color={palette.gray[500]} style={{ textAlign: 'center' }}>
          Social sign-in is coming soon — use email for now.
        </Mono>
      ) : null}
    </View>
  );
}
