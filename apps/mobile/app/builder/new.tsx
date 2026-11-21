import { router } from 'expo-router';
import { Blocks, Layers } from 'lucide-react-native';
import { useState } from 'react';
import { TextInput, View } from 'react-native';

import { startDraft } from '../../src/copilot/store';
import { ACCOUNT_SUBJECT } from '../../src/copilot/subjects';
import { WayRow } from '../../src/strategies/parts';
import { fonts, makeStyles, radius, useTheme } from '../../src/theme';
import { Button, Card, CopilotMark, ListRow, Screen, Text } from '../../src/ui';

/** A new strategy opens at once as an untitled draft with three ways to start (builder/start2 A). */
export default function NewStrategyScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const [idea, setIdea] = useState('');
  const back = { label: 'Strategies', onPress: () => (router.canGoBack() ? router.back() : router.replace('/strategies')) };

  const draftIt = () => {
    const text = idea.trim();
    if (!text) return;
    startDraft(text, ACCOUNT_SUBJECT).catch(() => undefined);
    router.push('/copilot/draft');
  };

  return (
    <Screen title="Untitled strategy" back={back} art="bold" artSeed="builder-new">
      <View style={s.meta}>
        <View style={s.tag}><Text variant="numSmall" tone="fg2">Draft</Text></View>
        <Text variant="small" tone="fg3">Not saved yet</Text>
      </View>

      <Card style={s.describe}>
        <Text variant="label" tone="fg3" style={s.caps}>DESCRIBE IT</Text>
        <TextInput
          value={idea}
          onChangeText={setIdea}
          multiline
          placeholder="Hold the strongest of a few stock ETFs, and move to bonds and gold when the market looks overbought."
          placeholderTextColor={c.fg3}
          style={s.input}
        />
        <View style={s.describeFoot}>
          <View style={s.copilot}>
            <CopilotMark size={14} color={c.accent} />
            <Text variant="caption" tone="fg2">Copilot drafts it</Text>
          </View>
          <Button label="Draft it" size="sm" onPress={draftIt} disabled={!idea.trim()} />
        </View>
      </Card>

      <Card style={s.group}>
        <WayRow icon={<Layers color={c.accent} size={16} strokeWidth={1.8} />} title="Copy a template" sub="Complete strategies, by category" onPress={() => router.push('/templates')} />
        <ListRow
          label={<View style={s.rowLabel}><Blocks color={c.fg3} size={16} strokeWidth={1.8} /><Text variant="body" tone="fg2">Add the first block</Text></View>}
          sub="Blocks are added in the web builder for now"
          last
        />
      </Card>

      <Text variant="subhead">Settings</Text>
      <Card style={s.group}>
        <ListRow label="Rebalance" value="Monthly" />
        <ListRow label="Benchmark" right={<Text variant="numSmall" tone="fg3">SPY</Text>} last />
      </Card>
      <Text variant="caption" tone="fg3">Needs at least one asset before it can be checked or saved.</Text>

      <View style={s.buttons}>
        <Button label="Backtest" variant="secondary" disabled onPress={() => undefined} style={s.flex} />
        <Button label="Save version 1" disabled onPress={() => undefined} style={s.flex} />
      </View>
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  meta: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: -8 },
  tag: { borderWidth: 1, borderStyle: 'dashed', borderColor: t.c.lineStrong, borderRadius: radius.xs, paddingHorizontal: 6, paddingVertical: 1 },
  describe: { gap: 10, ...t.shadow.md },
  caps: { letterSpacing: 0.8, fontFamily: fonts.mono, fontSize: 11 },
  input: { minHeight: 64, fontFamily: fonts.sans, fontSize: 14.5, lineHeight: 20, color: t.c.fg, textAlignVertical: 'top', padding: 0 },
  describeFoot: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  copilot: { flexDirection: 'row', alignItems: 'center', gap: 6 },
  group: { paddingVertical: 2 },
  rowLabel: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  buttons: { flexDirection: 'row', gap: 10 },
  flex: { flex: 1 },
}));
