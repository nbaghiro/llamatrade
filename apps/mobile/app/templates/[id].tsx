import { getTenantContext } from '@llamatrade/core/net';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { router, useLocalSearchParams } from 'expo-router';
import { useMemo, useState } from 'react';
import { View } from 'react-native';

import { readStrategy } from '../../src/builder/sentences';
import { SentenceView } from '../../src/builder/SentenceView';
import { strategyClient } from '../../src/net/clients';
import { templateMeta } from '../../src/strategies/templates';
import { useTemplates } from '../../src/strategies/useTemplates';
import { makeStyles } from '../../src/theme';
import { Button, Card, Loading, Notice, PanelError, Screen, Text } from '../../src/ui';

/** One template: what it holds and when, in sentences, and a way to copy it (preview2 A without its backtest). */
export default function TemplatePreviewScreen() {
  const s = useStyles();
  const { id } = useLocalSearchParams<{ id: string }>();
  const templates = useTemplates();
  const template = templates.status === 'ready' ? templates.value.find((t) => t.id === id) : undefined;
  const read = useMemo(() => (template ? readStrategy(template.configSexpr) : null), [template]);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const back = { label: 'Templates', onPress: () => (router.canGoBack() ? router.back() : router.replace('/templates')) };

  const use = async () => {
    if (!template) return;
    setCreating(true);
    setError(null);
    try {
      const res = await strategyClient.createStrategy({
        context: getTenantContext(),
        name: template.name,
        description: template.description,
        dslCode: template.configSexpr,
        templateId: template.id,
        symbols: read?.symbols ?? [],
      });
      const created = res.strategy;
      useStrategiesStore.getState().fetchStrategies();
      if (created) router.replace(`/builder/${created.id}`);
    } catch (e) {
      setError(e instanceof Error ? e.message : 'The strategy service did not respond.');
    } finally {
      setCreating(false);
    }
  };

  if (!template) {
    return (
      <Screen title="Template" back={back} art="bold" artSeed={`template-${id ?? ''}`}>
        {templates.status === 'loading' ? <Loading label="Loading the template" /> : <PanelError title="This template could not be found" onRetry={templates.retry} />}
      </Screen>
    );
  }

  return (
    <Screen title={template.name} back={back} eyebrow={templateMeta(template)} art="bold" artSeed={`template-${template.id}`}>
      {template.description ? <Text variant="small" tone="fg2" style={s.lead}>{template.description}</Text> : null}
      <Text variant="subhead">What it does</Text>
      <Card>
        {read ? <SentenceView sentences={read.sentences} /> : <Text variant="small" tone="fg3">The rules couldn't be read as sentences.</Text>}
      </Card>
      {read?.symbols.length ? (
        <View style={s.syms}>
          <Text variant="label" tone="fg3">Symbols</Text>
          <Text variant="numSmall" tone="fg2">{read.symbols.join('  ')}</Text>
        </View>
      ) : null}
      <Text variant="caption" tone="fg3">There's no stored backtest for this template yet. Using it saves a copy as version 1, which you can backtest straight away.</Text>
      {error ? <Notice title="The template wasn't copied." detail={error} /> : null}
      <Button label="Use this template" onPress={use} loading={creating} />
    </Screen>
  );
}

const useStyles = makeStyles(() => ({
  lead: { marginTop: -6 },
  syms: { gap: 4 },
}));
