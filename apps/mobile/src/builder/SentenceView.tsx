import { Fragment } from 'react';
import { View } from 'react-native';

import { fonts, makeStyles, useTheme } from '../theme';
import { Text } from '../ui';
import type { EditableValue, Piece } from './sentences';

/**
 * The strategy as paragraphs: symbols in mono, values underlined with a dotted line, and the
 * value being edited outlined in the accent. A changed value shows its new text.
 */
export function SentenceView({
  sentences,
  current,
  activeIndex,
  changed,
  onPick,
}: {
  sentences: Piece[][];
  /** The draft's value text by index, when it differs from the sentence's. */
  current?: Record<number, string>;
  activeIndex?: number | null;
  changed?: ReadonlySet<number>;
  onPick?: (value: EditableValue) => void;
}) {
  const s = useStyles();
  const { c } = useTheme();
  return (
    <View style={s.body}>
      {sentences.map((pieces, i) => (
        <Text key={i} variant="body" style={s.sentence}>
          {pieces.map((p, j) => {
            if (p.t === 'text') return p.text;
            if (p.t === 'sym') return <Text key={j} variant="body" style={s.sym}>{p.text}</Text>;
            const v = p.value;
            const active = activeIndex === v.index;
            const isChanged = changed?.has(v.index) ?? false;
            const tail = v.suffix.trimStart();
            const gap = v.suffix.slice(0, v.suffix.length - tail.length);
            return (
              <Fragment key={j}>
                <Text
                  variant="body"
                  onPress={onPick ? () => onPick(v) : undefined}
                  style={[
                    s.value,
                    v.kind === 'number' ? s.mono : null,
                    isChanged ? { color: c.accent } : null,
                    active ? { color: c.accent, backgroundColor: c.accentSoft } : null,
                  ]}
                >
                  {current?.[v.index] ?? v.text}
                </Text>
                {gap}
                {tail ? <Text variant="body" style={[s.suffix, v.kind === 'number' && tail === '%' ? s.mono : null]} onPress={onPick ? () => onPick(v) : undefined}>{tail}</Text> : null}
              </Fragment>
            );
          })}
        </Text>
      ))}
    </View>
  );
}

const useStyles = makeStyles((t) => ({
  body: { gap: 10 },
  sentence: { fontSize: 17, lineHeight: 28, color: t.c.fg },
  sym: { fontFamily: fonts.mono, fontSize: 15.5, lineHeight: 28, color: t.c.fg },
  mono: { fontFamily: fonts.mono, fontSize: 15.5, lineHeight: 28 },
  value: { fontSize: 17, lineHeight: 28, textDecorationLine: 'underline', textDecorationStyle: 'dotted', textDecorationColor: t.c.accent, color: t.c.fg },
  suffix: { fontSize: 17, lineHeight: 28, color: t.c.fg, textDecorationLine: 'underline', textDecorationStyle: 'dotted', textDecorationColor: t.c.accent },
}));
