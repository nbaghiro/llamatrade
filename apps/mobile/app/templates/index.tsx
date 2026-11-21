import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { ScrollView, View } from 'react-native';

import { readStrategy } from '../../src/builder/sentences';
import { groupByCategory, templateMeta } from '../../src/strategies/templates';
import { useTemplates } from '../../src/strategies/useTemplates';
import { makeStyles } from '../../src/theme';
import { Card, Loading, PanelError, Screen, Segmented, Text } from '../../src/ui';
import { cadence } from '../../src/ui/status';

/** Templates by category, each with its rules in a sentence (templates2 A without per-template backtests). */
export default function TemplatesScreen() {
  const s = useStyles();
  const templates = useTemplates();
  const groups = useMemo(() => (templates.status === 'ready' ? groupByCategory(templates.value) : []), [templates]);
  const [picked, setPicked] = useState<string | null>(null);
  const current = groups.find((g) => String(g.category) === picked) ?? groups[0];
  const back = { label: 'Strategies', onPress: () => (router.canGoBack() ? router.back() : router.replace('/strategies')) };

  return (
    <Screen title="Start from a template" back={back} eyebrow="Templates" art="bold" artSeed="templates">
      {templates.status === 'loading' ? (
        <Loading label="Loading templates" />
      ) : templates.status === 'error' ? (
        <PanelError title="Templates could not be loaded" detail="The strategy service didn't respond." onRetry={templates.retry} />
      ) : (
        <>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={s.chips}>
            <Segmented options={groups.map((g) => ({ key: String(g.category), label: g.label }))} value={String(current?.category ?? '')} onChange={setPicked} />
          </ScrollView>
          <View style={s.line}>
            <Text variant="subhead">{current?.label}</Text>
            <Text variant="small" tone="fg3">{current?.templates.length ?? 0} of {templates.value.length}</Text>
          </View>
          {current?.templates.map((t) => {
            const read = readStrategy(t.configSexpr);
            const rebalance = read?.values.find((v) => v.label === 'Rebalance')?.text ?? '';
            const firstRule = read?.sentences.find((ps) => !ps.some((p) => p.t === 'value' && p.value.label === 'Rebalance'));
            return (
              <Card key={t.id} onPress={() => router.push(`/templates/${t.id}`)} style={s.card}>
                <View style={s.line}>
                  <Text variant="caption" tone="fg3">{templateMeta(t)}</Text>
                  <Text variant="caption" tone="fg3">{cadence(rebalance)}</Text>
                </View>
                <Text variant="subhead">{t.name}</Text>
                {t.description ? <Text variant="small" tone="fg2" numberOfLines={3}>{t.description}</Text> : null}
                {firstRule ? (
                  <Text variant="small" tone="fg3" numberOfLines={2}>
                    {firstRule.map((p) => (p.t === 'value' ? `${p.value.text}${p.value.suffix}` : p.text)).join('')}
                  </Text>
                ) : null}
              </Card>
            );
          })}
          <Text variant="caption" tone="fg3">Backtest figures for templates aren't stored yet. Use a template, then backtest it to see how it would have done.</Text>
        </>
      )}
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  chips: { paddingRight: 20 },
  line: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  card: { gap: 6 },
}));
