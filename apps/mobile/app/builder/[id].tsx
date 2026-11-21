import { getTenantContext } from '@llamatrade/core/net';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { router, useLocalSearchParams } from 'expo-router';
import { CircleCheck, FlaskConical, MoveRight } from 'lucide-react-native';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';

import { backtestLikeLast } from '../../src/backtests/handoff';
import { checkCode, useDrafts } from '../../src/builder/drafts';
import { changeSummary, changesBetween, readStrategy, replaceValue, type Change, type EditableValue } from '../../src/builder/sentences';
import { SentenceView } from '../../src/builder/SentenceView';
import { Sheet } from '../../src/builder/Sheet';
import { ValueSheet } from '../../src/builder/ValueSheet';
import { openCopilot } from '../../src/copilot/store';
import { strategyClient } from '../../src/net/clients';
import { useSessionRows } from '../../src/sessions/data';
import { WayRow } from '../../src/strategies/parts';
import { makeStyles, radius, useTheme } from '../../src/theme';
import { Button, Card, CopilotMark, Loading, Notice, PanelError, Screen, Text } from '../../src/ui';

interface Saved {
  version: number;
  changes: Change[];
}

export default function BuilderScreen() {
  const s = useStyles();
  const { c } = useTheme();
  const { id } = useLocalSearchParams<{ id: string }>();
  const { strategies, details, detailLoading, fetchStrategyDetail } = useStrategiesStore();
  const draft = useDrafts((st) => (id ? st.drafts[id] : undefined));
  const setDraft = useDrafts((st) => st.setDraft);
  const discard = useDrafts((st) => st.discard);
  const rows = useSessionRows();
  const [editing, setEditing] = useState<EditableValue | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [saved, setSaved] = useState<Saved | null>(null);
  const [starting, setStarting] = useState(false);

  useEffect(() => {
    if (id) fetchStrategyDetail(id);
  }, [id, fetchStrategyDetail]);

  const strategy = (id ? details[id] : undefined) ?? strategies.find((x) => x.id === id);
  const savedCode = id && details[id] ? details[id].dslCode : '';
  const code = draft?.code ?? savedCode;
  const savedRead = useMemo(() => readStrategy(savedCode), [savedCode]);
  const read = useMemo(() => readStrategy(code), [code]);
  const changes = useMemo(() => (savedRead && read ? changesBetween(savedRead.values, read.values) : []), [savedRead, read]);
  const changed = useMemo(() => {
    const out = new Set<number>();
    if (savedRead && read) read.values.forEach((v, i) => savedRead.values[i]?.text !== v.text && out.add(i));
    return out;
  }, [savedRead, read]);
  const problems = useMemo(() => (code && code !== savedCode ? checkCode(code) : { errors: [], warnings: [] }), [code, savedCode]);
  const session = rows.find((r) => r.strategyId === id && r.state !== 'stopped');

  const back = { label: 'Strategies', onPress: () => (router.canGoBack() ? router.back() : router.replace('/strategies')) };

  if (!id || !strategy || !savedCode) {
    return (
      <Screen title="Strategy" back={back} art="bold" artSeed={`builder-${id ?? ''}`}>
        {id && detailLoading[id] !== false ? (
          <Loading label="Loading the rules" />
        ) : (
          <PanelError title="The rules could not be loaded" detail="The strategy service didn't respond." onRetry={id ? () => fetchStrategyDetail(id) : undefined} />
        )}
      </Screen>
    );
  }

  const nextVersion = strategy.version + 1;
  const meta = session
    ? session.version === strategy.version
      ? `runs in ${session.mode}`
      : `version ${session.version ?? '?'} runs in ${session.mode}`
    : 'not running';

  const save = async (nextCode: string) => {
    const after = readStrategy(nextCode);
    const list = savedRead && after ? changesBetween(savedRead.values, after.values) : [];
    const check = checkCode(nextCode);
    if (check.errors.length) {
      setDraft(id, { code: nextCode, baseVersion: strategy.version });
      setEditing(null);
      return;
    }
    setSaving(true);
    setSaveError(null);
    try {
      const res = await strategyClient.updateStrategy({
        context: getTenantContext(),
        strategyId: id,
        name: strategy.name,
        description: strategy.description,
        dslCode: nextCode,
        symbols: strategy.symbols,
        changeSummary: changeSummary(list) || 'Edited on the phone',
      });
      discard(id);
      setEditing(null);
      await fetchStrategyDetail(id);
      setSaved({ version: res.strategy?.version ?? nextVersion, changes: list });
    } catch (e) {
      setDraft(id, { code: nextCode, baseVersion: strategy.version });
      setEditing(null);
      setSaveError(e instanceof Error ? e.message : 'The strategy service did not respond.');
    } finally {
      setSaving(false);
    }
  };

  const runBacktest = async (version: number) => {
    setStarting(true);
    const runId = await backtestLikeLast(id, version);
    setStarting(false);
    setSaved(null);
    router.push(runId ? `/backtests/${runId}` : `/backtests/new?strategy=${id}&version=${version}`);
  };

  const savedValue = (v: EditableValue | null) => (v && savedRead ? savedRead.values[v.index]?.text ?? null : null);

  return (
    <Screen
      title={strategy.name}
      back={back}
      art="bold"
      artSeed={`builder-${id}`}
      right={
        <Pressable accessibilityRole="button" accessibilityLabel="Ask Copilot about this strategy" hitSlop={8} onPress={() => openCopilot({ kind: 'strategy', id })}>
          <CopilotMark size={20} color={c.accent} />
        </Pressable>
      }
    >
      <View style={s.meta}>
        <View style={s.ver}><Text variant="numSmall" tone="fg2">{changes.length ? `v${nextVersion} draft` : `Version ${strategy.version}`}</Text></View>
        <Text variant="small" tone="fg3">{changes.length ? `${changes.length} ${changes.length === 1 ? 'change' : 'changes'}, kept in the app until you save` : meta}</Text>
      </View>

      {read ? (
        <SentenceView sentences={read.sentences} changed={changed} activeIndex={editing?.index ?? null} onPick={setEditing} />
      ) : (
        <Notice title="These rules can't be read as sentences." detail="Open the strategy on the web to edit its code." />
      )}

      <Text variant="caption" tone="fg3">Tap an underlined value to change it. Adding or removing rules needs Copilot or the web builder.</Text>

      {saveError ? <Notice title="The version wasn't saved." detail={`${saveError} Your change is kept as a draft.`} /> : null}

      {problems.errors.length || problems.warnings.length ? (
        <Card style={s.problems}>
          {problems.errors.map((m) => (
            <View key={m} style={s.problem}>
              <Text variant="smallStrong" tone="risk">{m}</Text>
              <Text variant="caption" tone="fg3">Error, must be fixed to save</Text>
            </View>
          ))}
          {problems.warnings.map((m) => (
            <View key={m} style={s.problem}>
              <Text variant="small">{m}</Text>
              <Text variant="caption" tone="fg3">Warning</Text>
            </View>
          ))}
        </Card>
      ) : null}

      {changes.length ? (
        <Card style={s.changes}>
          <Text variant="label" tone="fg3">Changes in this draft</Text>
          {changes.map((ch) => (
            <View key={ch.label} style={s.changeRow}>
              <Text variant="small" style={s.flex}>{ch.label}</Text>
              <Text variant="numSmall" tone="fg3" style={s.was}>{ch.from}</Text>
              <Text variant="numSmall">{ch.to}</Text>
            </View>
          ))}
          <View style={s.buttons}>
            <Button label="Discard" variant="secondary" onPress={() => discard(id)} style={s.flex} />
            <Button
              label={problems.errors.length ? `Fix ${problems.errors.length} ${problems.errors.length === 1 ? 'error' : 'errors'} to save` : `Save version ${nextVersion}`}
              disabled={problems.errors.length > 0}
              loading={saving}
              onPress={() => save(code)}
              style={s.flex}
            />
          </View>
        </Card>
      ) : (
        <Button label={`Backtest version ${strategy.version}`} variant="secondary" loading={starting} onPress={() => runBacktest(strategy.version)} />
      )}

      <ValueSheet
        value={editing}
        saved={savedValue(editing)}
        onClose={() => setEditing(null)}
        saveLabel={`Save version ${nextVersion}`}
        saving={saving}
        onSave={(text) => editing && save(replaceValue(code, editing, text))}
      />

      <Sheet visible={saved !== null} onClose={() => setSaved(null)}>
        {saved ? (
          <>
            <View style={s.savedHead}>
              <CircleCheck color={c.accent} size={20} strokeWidth={1.8} />
              <Text variant="heading">Saved as version {saved.version}</Text>
            </View>
            {saved.changes.length ? (
              <Text variant="small" tone="fg2">{saved.changes.map((ch) => `${ch.label} ${ch.from} to ${ch.to}`).join(', ')}.</Text>
            ) : null}
            <View style={s.savedRows}>
              <WayRow
                icon={<FlaskConical color={c.fg2} size={16} strokeWidth={1.8} />}
                title={`Backtest version ${saved.version}`}
                sub="Same settings as the last run"
                onPress={() => runBacktest(saved.version)}
                last={!session}
              />
              {session ? (
                <WayRow
                  icon={<MoveRight color={c.fg2} size={16} strokeWidth={1.8} />}
                  title={`Switch the ${session.mode} session`}
                  sub={`It runs version ${session.version ?? strategy.version - 1} until you do`}
                  onPress={() => {
                    setSaved(null);
                    router.push(`/sessions/${session.id}`);
                  }}
                  last
                />
              ) : null}
            </View>
            <Button label={`Backtest version ${saved.version}`} loading={starting} onPress={() => runBacktest(saved.version)} />
            <Button label="Keep editing" variant="secondary" onPress={() => setSaved(null)} />
          </>
        ) : null}
      </Sheet>
    </Screen>
  );
}

const useStyles = makeStyles((t) => ({
  meta: { flexDirection: 'row', alignItems: 'center', gap: 8, marginTop: -8 },
  ver: { borderWidth: 1, borderColor: t.c.lineStrong, borderRadius: radius.xs, paddingHorizontal: 6, paddingVertical: 1 },
  problems: { gap: 10 },
  problem: { gap: 2 },
  changes: { gap: 8 },
  changeRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  was: { textDecorationLine: 'line-through' },
  flex: { flex: 1 },
  buttons: { flexDirection: 'row', gap: 10, marginTop: 6 },
  savedHead: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  savedRows: { backgroundColor: t.c.sunk, borderRadius: radius.md, paddingHorizontal: 12 },
}));
