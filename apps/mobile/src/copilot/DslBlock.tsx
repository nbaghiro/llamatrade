import { ScrollView, Text } from 'react-native';

import { fonts, palette } from '../theme';

const KEYWORDS = new Set(['strategy', 'if', 'else', 'weight', 'filter', 'asset', 'group', 'portfolio']);
const C = {
  kw: '#ff8c6b',
  param: '#e0a3ff',
  str: '#7fd39b',
  num: '#8fb7ff',
  punct: '#8a8577',
  text: '#e9e4d6',
};

function colorFor(tok: string): string {
  if (tok === '(' || tok === ')') return C.punct;
  if (tok.startsWith('"')) return C.str;
  if (tok.startsWith(':')) return C.param;
  if (/^-?[0-9]/.test(tok)) return C.num;
  if (KEYWORDS.has(tok)) return C.kw;
  return C.text;
}

/** Read-only DSL viewer — the mobile analogue of the web DslCodeBlock. */
export function DslBlock({ code }: { code: string }) {
  const parts = code.match(/"(?:[^"\\]|\\.)*"|[()]|\s+|[^\s()]+/g) ?? [code];
  return (
    <ScrollView
      horizontal
      showsHorizontalScrollIndicator={false}
      style={{ backgroundColor: palette.ink, borderWidth: 2, borderColor: palette.ink }}
      contentContainerStyle={{ padding: 12 }}
    >
      <Text style={{ fontFamily: fonts.mono, fontSize: 11, lineHeight: 18 }}>
        {parts.map((p, i) =>
          /^\s+$/.test(p) ? (
            <Text key={i}>{p}</Text>
          ) : (
            <Text key={i} style={{ color: colorFor(p) }}>
              {p}
            </Text>
          ),
        )}
      </Text>
    </ScrollView>
  );
}
