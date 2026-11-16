import type { ReactNode } from 'react';
import { Linking, Text, View } from 'react-native';

import { fonts, radius, useTheme, type Colors } from '../theme';

interface Palette {
  text: string;
  dim: string;
  codeBg: string;
  link: string;
  rule: string;
  fenceBg: string;
  fenceBorder: string;
}

function paletteFor(c: Colors): Palette {
  return { text: c.fg, dim: c.fg3, codeBg: c.sunk, link: c.accent, rule: c.line, fenceBg: c.sunk, fenceBorder: c.line };
}

const INLINE = /(\*\*[^*]+\*\*|\*[^*]+\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;

/** Inline spans (bold / italic / code chip / link) for one line, as <Text> children. */
function inline(content: string, p: Palette, keyBase: string): ReactNode[] {
  return content.split(INLINE).map((seg, i) => {
    const key = `${keyBase}-${i}`;
    if (seg.startsWith('**') && seg.endsWith('**')) {
      return (
        <Text key={key} style={{ fontFamily: fonts.semibold }}>
          {seg.slice(2, -2)}
        </Text>
      );
    }
    if (seg.startsWith('*') && seg.endsWith('*')) {
      return (
        <Text key={key} style={{ fontStyle: 'italic' }}>
          {seg.slice(1, -1)}
        </Text>
      );
    }
    if (seg.startsWith('`') && seg.endsWith('`')) {
      return (
        <Text
          key={key}
          style={{
            fontFamily: fonts.mono,
            fontSize: 11.5,
            color: p.text,
            backgroundColor: p.codeBg,
          }}
        >
          {' '}
          {seg.slice(1, -1)}{' '}
        </Text>
      );
    }
    const link = seg.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (link) {
      return (
        <Text key={key} style={{ color: p.link, textDecorationLine: 'underline' }} onPress={() => Linking.openURL(link[2])}>
          {link[1]}
        </Text>
      );
    }
    return <Text key={key}>{seg}</Text>;
  });
}

function Fence({ code, language, p }: { code: string; language: string; p: Palette }) {
  return (
    <View style={{ marginVertical: 8, backgroundColor: p.fenceBg, borderWidth: 1, borderColor: p.fenceBorder, borderRadius: radius.md, padding: 12 }}>
      <Text style={{ fontFamily: fonts.sans, fontSize: 11, color: p.dim, marginBottom: 6 }}>{language}</Text>
      <Text style={{ fontFamily: fonts.mono, fontSize: 12, lineHeight: 18, color: p.text }}>{code}</Text>
    </View>
  );
}

const HEADER_SIZE: Record<number, number> = { 1: 19, 2: 17, 3: 15, 4: 14, 5: 13, 6: 12 };

/** Markdown for Copilot messages: paragraphs, headings, lists, rules, inline code and links. */
export function Markdown({ content, size = 14 }: { content: string; size?: number }) {
  const { c } = useTheme();
  const p = paletteFor(c);
  const base = { fontFamily: fonts.sans, fontSize: size, lineHeight: size * 1.5, color: p.text } as const;

  // Split into code fences vs prose.
  const parts = content.split(/(```[\s\S]*?```)/g);
  const blocks: ReactNode[] = [];

  parts.forEach((part, pi) => {
    if (part.startsWith('```') && part.endsWith('```')) {
      const lines = part.slice(3, -3).split('\n');
      const language = lines[0].trim() || 'text';
      const code = lines.slice(1).join('\n').replace(/\n+$/, '');
      if (code.trim()) blocks.push(<Fence key={`f-${pi}`} code={code} language={language} p={p} />);
      return;
    }

    // Prose: line-by-line into headers / rules / lists / paragraphs.
    const lines = part.split('\n');
    let list: { ordered: boolean; items: string[] } | null = null;
    let lk = 0;

    const flush = () => {
      if (!list) return;
      const cur = list;
      blocks.push(
        <View key={`l-${pi}-${lk++}`} style={{ marginVertical: 6, gap: 3 }}>
          {cur.items.map((it, i) => (
            <View key={i} style={{ flexDirection: 'row', gap: 7 }}>
              <Text style={[base, { color: p.dim }]}>{cur.ordered ? `${i + 1}.` : '•'}</Text>
              <Text style={[base, { flex: 1 }]}>{inline(it, p, `li-${pi}-${lk}-${i}`)}</Text>
            </View>
          ))}
        </View>,
      );
      list = null;
    };

    lines.forEach((line, li) => {
      const t = line.trim();
      if (!t) {
        flush();
        return;
      }
      const h = t.match(/^(#{1,6})\s+(.+)$/);
      if (h) {
        flush();
        const lvl = h[1].length;
        blocks.push(
          <Text key={`h-${pi}-${li}`} style={[base, { fontFamily: fonts.semibold, fontSize: HEADER_SIZE[lvl], lineHeight: HEADER_SIZE[lvl] * 1.3, marginTop: 8, marginBottom: 3 }]}>
            {inline(h[2], p, `h-${pi}-${li}`)}
          </Text>,
        );
        return;
      }
      if (/^[-*_]{3,}$/.test(t)) {
        flush();
        blocks.push(<View key={`hr-${pi}-${li}`} style={{ height: 1, backgroundColor: p.rule, marginVertical: 10 }} />);
        return;
      }
      const ul = t.match(/^[-*+]\s+(.+)$/);
      if (ul) {
        if (!list || list.ordered) {
          flush();
          list = { ordered: false, items: [] };
        }
        list.items.push(ul[1]);
        return;
      }
      const ol = t.match(/^\d+[.)]\s+(.+)$/);
      if (ol) {
        if (!list || !list.ordered) {
          flush();
          list = { ordered: true, items: [] };
        }
        list.items.push(ol[1]);
        return;
      }
      flush();
      blocks.push(
        <Text key={`p-${pi}-${li}`} style={[base, { marginVertical: 3 }]}>
          {inline(line, p, `p-${pi}-${li}`)}
        </Text>,
      );
    });
    flush();
  });

  return <View>{blocks}</View>;
}
