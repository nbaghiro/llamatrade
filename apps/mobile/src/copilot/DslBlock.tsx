import { ScrollView, Text } from 'react-native';

import { fonts, makeStyles, radius, useTheme, type Colors } from '../theme';

const KEYWORDS = new Set(['strategy', 'if', 'else', 'weight', 'filter', 'asset', 'group', 'portfolio']);

function colorFor(tok: string, c: Colors): string {
  if (tok === '(' || tok === ')') return c.fg3;
  if (tok.startsWith('"')) return c.fg2;
  if (tok.startsWith(':')) return c.fg2;
  if (/^-?[0-9]/.test(tok)) return c.fg;
  if (KEYWORDS.has(tok)) return c.accent;
  return c.fg;
}

/** Read-only strategy DSL with light syntax colour. */
export function DslBlock({ code }: { code: string }) {
  const { c } = useTheme();
  const s = useStyles();
  const parts = code.match(/"(?:[^"\\]|\\.)*"|[()]|\s+|[^\s()]+/g) ?? [code];
  return (
    <ScrollView horizontal showsHorizontalScrollIndicator={false} style={s.box} contentContainerStyle={s.content}>
      <Text style={s.code} selectable>
        {parts.map((p, i) =>
          /^\s+$/.test(p) ? (
            <Text key={i}>{p}</Text>
          ) : (
            <Text key={i} style={{ color: colorFor(p, c) }}>
              {p}
            </Text>
          ),
        )}
      </Text>
    </ScrollView>
  );
}

const useStyles = makeStyles((t) => ({
  box: { backgroundColor: t.c.sunk, borderWidth: 1, borderColor: t.c.line, borderRadius: radius.md },
  content: { padding: 12 },
  code: { fontFamily: fonts.mono, fontSize: 12, lineHeight: 18, color: t.c.fg },
}));
