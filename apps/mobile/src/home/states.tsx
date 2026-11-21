/** Home's other states: the first visit (first-visit2 B) and the recap after the close (quiet A). */

import { signedMoney } from '@llamatrade/core/format';
import { router } from 'expo-router';
import { ChevronRight, LayoutGrid } from 'lucide-react-native';
import type { ReactNode } from 'react';
import { Pressable, View } from 'react-native';

import { Sparkline } from '../charts/Sparkline';
import { openCopilot } from '../copilot/store';
import { series } from '../ui/candleArt';
import { makeStyles, radius, useTheme } from '../theme';
import { Button, Card, CopilotMark, Text, pnlTone } from '../ui';
import type { Mode } from './model';
import { PaperAmount } from './PaperAmount';
import { SectionHead } from './parts';
import { openLabel } from './when';

/** Three ways to make a first strategy, each card showing what the path looks like. */
export function FirstVisit({ name }: { name: string | null }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <View style={s.first}>
      <View style={s.firstHead}>
        <Text variant="title">{name ? `Welcome, ${name}.` : 'Welcome.'}</Text>
        <Text variant="body" tone="fg2">
          How would you like to start?
        </Text>
      </View>
      <Card style={s.templateCard} onPress={() => router.push('/templates')}>
        <TemplatePreview />
        <View style={s.templateBody}>
          <Text variant="subhead">Start from a template</Text>
          <Text variant="small" tone="fg2">
            Ready-made strategies you can backtest before changing anything.
          </Text>
          <Button label="Browse templates" onPress={() => router.push('/templates')} style={s.templateButton} />
        </View>
      </Card>
      <WayCard
        icon={<CopilotMark size={22} />}
        title="Describe it to Copilot"
        detail="Write the idea in a sentence."
        onPress={() => openCopilot({ kind: 'account', id: 'account' })}
      />
      <WayCard
        icon={<LayoutGrid color={c.accent} size={22} strokeWidth={1.7} />}
        title="Build from blocks"
        detail="Set the rules yourself."
        onPress={() => router.push('/builder/new')}
      />
      <Text variant="caption" tone="fg3" style={s.center}>
        You can connect Alpaca paper later.
      </Text>
    </View>
  );
}

/** An illustrative line for the template card, drawn from the candle generator; it shows no figures. */
function TemplatePreview() {
  const s = useStyles();
  return (
    <View style={s.preview}>
      <Text variant="label" tone="fg3">Illustration</Text>
      <Sparkline values={PREVIEW} width={300} height={52} strokeWidth={1.8} />
    </View>
  );
}

const PREVIEW = series(7, 60, 0.6, 0.018);

function WayCard({ icon, title, detail, onPress }: { icon: ReactNode; title: string; detail: string; onPress: () => void }) {
  const { c } = useTheme();
  const s = useStyles();
  return (
    <Card onPress={onPress} style={s.way}>
      <View style={s.wayIcon}>{icon}</View>
      <View style={s.flex}>
        <Text variant="bodyStrong">{title}</Text>
        <Text variant="small" tone="fg2">
          {detail}
        </Text>
      </View>
      <ChevronRight color={c.fg3} size={18} strokeWidth={1.8} />
    </Card>
  );
}

/** After the close: what each session added today and when the market opens next. */
export function ClosedRecap({
  recap,
  nextOpen,
  now,
  waiting,
  onOpen,
}: {
  recap: readonly { id: string; name: string; mode: Mode; today: number }[];
  nextOpen: Date | null;
  now: number;
  /** Sessions held back until someone acts, e.g. frozen. */
  waiting: readonly string[];
  onOpen: (id: string) => void;
}) {
  const s = useStyles();
  return (
    <>
      {recap.length ? (
        <>
          <SectionHead title="How the day closed" />
          <Card style={s.list}>
            {recap.map((r, i) => (
              <Pressable
                key={r.id}
                onPress={() => onOpen(r.id)}
                style={({ pressed }) => [s.recapRow, i < recap.length - 1 ? s.divider : null, pressed ? s.pressed : null]}
              >
                <View style={s.flex}>
                  <Text variant="bodyStrong">{r.name}</Text>
                  <Text variant="caption" tone="fg3">
                    {r.mode === 'live' ? 'Live' : 'Paper'}
                  </Text>
                </View>
                <PaperAmount paper={r.mode === 'paper'} variant="numStrong" tone={pnlTone(r.today)}>
                  {signedMoney(r.today, 2)}
                </PaperAmount>
              </Pressable>
            ))}
          </Card>
        </>
      ) : null}
      <SectionHead title="Next" />
      <Card style={s.list}>
        <View style={[s.nextRow, waiting.length ? s.divider : null]}>
          <Text variant="numSmall" tone="fg3" style={s.when}>
            {nextOpen ? openLabel(nextOpen.getTime(), now) : 'Unknown'}
          </Text>
          <Text variant="small" style={s.flex}>
            {nextOpen ? 'The market opens' : "The next open couldn't be read."}
          </Text>
        </View>
        {waiting.map((w, i) => (
          <View key={w} style={[s.nextRow, i < waiting.length - 1 ? s.divider : null]}>
            <Text variant="numSmall" tone="fg3" style={s.when}>
              Waiting
            </Text>
            <Text variant="small" style={s.flex}>
              {w} <Text variant="small" tone="risk">waits on review</Text>
            </Text>
          </View>
        ))}
      </Card>
    </>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  pressed: { opacity: 0.7 },
  center: { textAlign: 'center' },
  first: { gap: 12 },
  firstHead: { gap: 4, marginBottom: 4 },
  templateCard: { padding: 0, overflow: 'hidden' },
  preview: { padding: 14, gap: 10, backgroundColor: t.c.sunk, borderBottomWidth: 1, borderColor: t.c.line },
  templateBody: { padding: 14, gap: 4 },
  templateButton: { marginTop: 10 },
  way: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  wayIcon: {
    width: 52,
    height: 52,
    borderRadius: radius.md,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: t.c.sunk,
  },
  list: { paddingVertical: 2 },
  divider: { borderBottomWidth: 1, borderColor: t.c.line },
  recapRow: { flexDirection: 'row', alignItems: 'center', gap: 10, paddingVertical: 12 },
  nextRow: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 11 },
  when: { width: 96 },
}));
