import { buildMeta, formatDSL, parsePreview } from '@llamatrade/core/agent/artifact';
import { ArtifactType, type PendingArtifact } from '@llamatrade/core/proto/agent_pb';
import { useAgentStore } from '@llamatrade/core/stores/agent';
import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { View } from 'react-native';

import { makeStyles } from '../theme';
import { Button, Card, Pill, Text } from '../ui';
import { DslBlock } from './DslBlock';

/** A drafted strategy in the conversation: Save commits it, Open shows the saved strategy. */
export function ArtifactCard({ artifact }: { artifact: PendingArtifact }) {
  const s = useStyles();
  const commit = useAgentStore((st) => st.commitArtifact);
  const [saving, setSaving] = useState(false);

  const preview = useMemo(() => parsePreview(artifact), [artifact]);
  const dsl = useMemo(() => (preview?.dsl_code ? formatDSL(preview.dsl_code) : ''), [preview]);
  const meta = useMemo(() => buildMeta(dsl, preview), [dsl, preview]);

  const isStrategy = artifact.artifactType === ArtifactType.STRATEGY;
  const isSaved = artifact.isCommitted;
  const savedId = artifact.committedResourceId;

  const onSave = async () => {
    if (isSaved || saving) return;
    setSaving(true);
    try {
      await commit(artifact.id);
    } finally {
      setSaving(false);
    }
  };

  return (
    <Card style={s.card}>
      <View style={s.head}>
        <Text variant="subhead" numberOfLines={1} style={s.name}>
          {artifact.name || (isStrategy ? 'Strategy' : 'Draft')}
        </Text>
        <Pill label={isSaved ? 'Saved' : 'Draft'} tone="accent" />
      </View>
      {meta ? <Text variant="small" tone="fg3">{meta}</Text> : null}
      {dsl ? (
        <DslBlock code={dsl} />
      ) : artifact.description ? (
        <Text variant="small" tone="fg2">{artifact.description}</Text>
      ) : null}
      <View style={s.actions}>
        <Button
          label={isSaved ? 'Saved' : saving ? 'Saving' : 'Save'}
          onPress={onSave}
          loading={saving}
          disabled={isSaved || !dsl}
          style={s.action}
        />
        <Button
          label="Open"
          variant="secondary"
          onPress={() => router.push(`/strategy/${savedId}`)}
          disabled={!isSaved || !savedId}
          style={s.action}
        />
      </View>
      <Text variant="caption" tone="fg3">Edit it or run a backtest in the web builder.</Text>
    </Card>
  );
}

const useStyles = makeStyles(() => ({
  card: { alignSelf: 'stretch', gap: 10 },
  head: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  name: { flexShrink: 1 },
  actions: { flexDirection: 'row', gap: 8 },
  action: { flex: 1 },
}));
