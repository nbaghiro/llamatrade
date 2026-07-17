import { Check, FlaskConical, Sparkles } from 'lucide-react-native';
import { useMemo, useState } from 'react';
import { ActivityIndicator, Pressable, View } from 'react-native';

import { ArtifactType, type PendingArtifact } from '@llamatrade/core/proto/agent_pb';
import { useAgentStore } from '@llamatrade/core/stores/agent';
import { palette } from '../theme';
import { Badge, Body, Mono } from '../ui';
import { buildMeta, formatDSL, parsePreview } from '@llamatrade/core/agent/artifact';
import { DslBlock } from './DslBlock';

/**
 * Inline draft-strategy card — the "approve" surface. Save commits the artifact
 * server-side (agent.commitArtifact); editing/backtesting stay on the desktop
 * builder (deep-linked from there).
 */
export function ArtifactCard({ artifact }: { artifact: PendingArtifact }) {
  const commit = useAgentStore((s) => s.commitArtifact);
  const [saving, setSaving] = useState(false);

  const preview = useMemo(() => parsePreview(artifact), [artifact]);
  const dsl = useMemo(() => (preview?.dsl_code ? formatDSL(preview.dsl_code) : ''), [preview]);
  const meta = useMemo(() => buildMeta(dsl, preview), [dsl, preview]);

  const isStrategy = artifact.artifactType === ArtifactType.STRATEGY;
  const isSaved = artifact.isCommitted;

  const onSave = async () => {
    if (isSaved || saving) return;
    setSaving(true);
    await commit(artifact.id);
    setSaving(false);
  };

  return (
    <View
      style={{
        alignSelf: 'stretch',
        borderWidth: 2,
        borderColor: palette.ink,
        backgroundColor: palette.paper,
      }}
    >
      {/* Header */}
      <View
        style={{
          flexDirection: 'row',
          alignItems: 'center',
          gap: 7,
          borderBottomWidth: 2,
          borderColor: palette.ink,
          backgroundColor: palette.bone,
          paddingHorizontal: 11,
          paddingVertical: 9,
        }}
      >
        <Sparkles color={palette.orange[500]} size={13} strokeWidth={2} />
        <Mono size={9} color={palette.gray[500]} style={{ fontWeight: '700' }}>
          {isStrategy ? 'STRATEGY' : 'ARTIFACT'}
        </Mono>
        <Body size={13} style={{ fontWeight: '700', flexShrink: 1 }} numberOfLines={1}>
          {artifact.name || 'Strategy'}
        </Body>
        <View style={{ marginLeft: 'auto' }}>
          <Badge label={isSaved ? 'Saved' : 'Draft'} variant={isSaved ? 'green' : 'orange'} />
        </View>
      </View>

      {meta ? (
        <Mono size={9.5} color={palette.gray[500]} style={{ paddingHorizontal: 11, paddingTop: 9, textTransform: 'uppercase' }}>
          {meta}
        </Mono>
      ) : null}

      {dsl ? (
        <View style={{ margin: 11 }}>
          <DslBlock code={dsl} />
        </View>
      ) : artifact.description ? (
        <Body size={13} color={palette.gray[600]} style={{ paddingHorizontal: 11, paddingVertical: 11 }}>
          {artifact.description}
        </Body>
      ) : null}

      {/* Actions */}
      <View style={{ borderTopWidth: 2, borderColor: palette.ink, padding: 11, gap: 8 }}>
        <Pressable
          onPress={onSave}
          disabled={isSaved || saving || !dsl}
          style={{
            backgroundColor: isSaved ? palette.green[500] : palette.orange[500],
            borderWidth: 2,
            borderColor: palette.ink,
            paddingVertical: 10,
            flexDirection: 'row',
            alignItems: 'center',
            justifyContent: 'center',
            gap: 7,
            opacity: !dsl ? 0.4 : 1,
          }}
        >
          {saving ? (
            <ActivityIndicator size="small" color={palette.ink} />
          ) : isSaved ? (
            <Check color={palette.bone} size={14} strokeWidth={2.5} />
          ) : (
            <FlaskConical color={palette.ink} size={14} strokeWidth={2} />
          )}
          <Mono size={11} color={isSaved ? palette.bone : palette.ink} style={{ fontWeight: '700' }}>
            {isSaved ? 'SAVED' : saving ? 'SAVING…' : 'SAVE STRATEGY'}
          </Mono>
        </Pressable>
        <Mono size={9} color={palette.gray[500]} style={{ textAlign: 'center' }}>
          Open in the desktop builder to edit or backtest
        </Mono>
      </View>
    </View>
  );
}
