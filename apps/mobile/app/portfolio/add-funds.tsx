import { money } from '@llamatrade/core/format';
import { useFundingStore } from '@llamatrade/core/stores/funding';
import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';

import { SplitBar } from '../../src/charts/SplitBar';
import { useHomeData } from '../../src/home/data';
import { displayName } from '../../src/home/model';
import { parseAmount } from '../../src/portfolio/model';
import { moveToSession } from '../../src/portfolio/funding';
import { makeStyles, radius } from '../../src/theme';
import { Button, Card, Field, Notice, Screen, Text } from '../../src/ui';

type Step = 1 | 2 | 3 | 'done';
const QUICK = [1000, 5000, 10000];

/** Add paper funds, then place them (add-funds2 A): amount, where it goes, confirm with now and after. */
export default function AddFundsScreen() {
  const s = useStyles();
  const d = useHomeData();
  const { addFunds, submitting, error: fundError } = useFundingStore();
  const [step, setStep] = useState<Step>(1);
  const [text, setText] = useState('');
  const [target, setTarget] = useState<string>('unallocated');
  const [error, setError] = useState<string | null>(null);
  const [moving, setMoving] = useState(false);
  const amount = parseAmount(text);

  const paper = useMemo(() => d.sessions.filter((x) => x.mode === 'paper'), [d.sessions]);
  const chosen = paper.find((x) => x.sleeveId === target) ?? null;
  const back = () => (router.canGoBack() ? router.back() : router.replace('/portfolio'));

  const bars = (after: boolean) => {
    const add = after ? (amount ?? 0) : 0;
    return [
      ...paper
        .filter((x) => x.state !== 'stopped')
        .map((x) => ({ key: x.id, value: (x.value ?? 0) + (x.sleeveId === target ? add : 0), look: 'hatched' as const })),
      { key: 'cash', value: (d.paperCash ?? 0) + (target === 'unallocated' ? add : 0), look: 'muted' as const },
    ];
  };

  const confirm = async () => {
    if (amount === null) return;
    setError(null);
    const free = await addFunds(amount);
    if (free === null) return;
    if (chosen?.sleeveId) {
      setMoving(true);
      const err = await moveToSession(chosen.sleeveId, amount);
      setMoving(false);
      if (err) {
        setError(`The funds were added to unallocated cash, but couldn't be moved to ${displayName(chosen.name)}: ${err}`);
        await d.refresh();
        return;
      }
    }
    await d.refresh();
    setStep('done');
  };

  return (
    <Screen title="Add paper funds" art="bold" artSeed="portfolio-add-funds" back={{ label: 'Portfolio', onPress: back }}>
      <Text variant="label" tone="fg3">
        {step === 'done' ? 'DONE' : `STEP ${step} OF 3`}
      </Text>

      {step === 1 ? (
        <Card style={s.card}>
          <Field label="Amount" value={text} onChange={setText} placeholder="$10,000" keyboardType="decimal-pad" mono />
          <View style={s.quick}>
            {QUICK.map((q) => (
              <Pressable key={q} accessibilityRole="button" onPress={() => setText(String(q))} style={s.chip}>
                <Text variant="numSmall">{money(q)}</Text>
              </Pressable>
            ))}
          </View>
          <Text variant="small" tone="fg3">
            Paper funds are simulated and only change your paper account. Live money is added in Alpaca.
          </Text>
          <Button label="Continue" disabled={amount === null} onPress={() => setStep(2)} />
        </Card>
      ) : null}

      {step === 2 ? (
        <Card style={s.card}>
          <Text variant="subhead">Where {amount !== null ? money(amount, 2) : 'it'} goes</Text>
          <Choice
            title="Keep it unallocated"
            detail="It waits as free cash until you start or top up a session."
            selected={target === 'unallocated'}
            onPress={() => setTarget('unallocated')}
          />
          {paper.map((x) => {
            const stopped = x.state === 'stopped';
            const disabled = stopped || !x.sleeveId;
            return (
              <Choice
                key={x.id}
                title={`Top up ${displayName(x.name)}`}
                detail={stopped ? "Stopped sessions can't take money." : !x.sleeveId ? "This session's sleeve couldn't be read." : "Moves to the session's cash. It invests by its own rules."}
                selected={target === x.sleeveId}
                disabled={disabled}
                onPress={() => x.sleeveId && setTarget(x.sleeveId)}
              />
            );
          })}
          <View style={s.actions}>
            <Button label="Back" variant="secondary" onPress={() => setStep(1)} style={s.flex} />
            <Button label="Continue" onPress={() => setStep(3)} style={s.flex} />
          </View>
        </Card>
      ) : null}

      {step === 3 && amount !== null ? (
        <Card style={s.card}>
          <Text variant="subhead">
            Add {money(amount, 2)} paper funds{chosen ? ` to ${displayName(chosen.name)}` : ', unallocated'}
          </Text>
          <View style={s.barRow}>
            <Text variant="small" tone="fg3" style={s.barLabel}>
              Now
            </Text>
            <View style={s.flex}>
              <SplitBar segments={bars(false)} height={10} />
            </View>
          </View>
          <View style={s.barRow}>
            <Text variant="small" tone="fg3" style={s.barLabel}>
              After
            </Text>
            <View style={s.flex}>
              <SplitBar segments={bars(true)} height={10} />
            </View>
          </View>
          <Text variant="caption" tone="fg3">
            Your paper sessions, then unallocated cash in grey.
          </Text>
          {error || fundError ? <Notice title={error ?? fundError ?? ''} /> : null}
          <View style={s.actions}>
            <Button label="Back" variant="secondary" onPress={() => setStep(2)} style={s.flex} />
            <Button label="Add funds" loading={submitting || moving} onPress={confirm} style={s.flex} />
          </View>
        </Card>
      ) : null}

      {step === 'done' ? (
        <Card style={s.card}>
          <Text variant="subhead">
            {amount !== null ? money(amount, 2) : 'The funds'} added{chosen ? ` to ${displayName(chosen.name)}` : ' to unallocated cash'}.
          </Text>
          <Text variant="small" tone="fg2">
            It shows on Portfolio and in Activity now.
          </Text>
          <Button label="Back to Portfolio" onPress={back} />
        </Card>
      ) : null}
    </Screen>
  );
}

function Choice({
  title,
  detail,
  selected,
  disabled = false,
  onPress,
}: {
  title: string;
  detail: string;
  selected: boolean;
  disabled?: boolean;
  onPress: () => void;
}) {
  const s = useStyles();
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ selected, disabled }}
      disabled={disabled}
      onPress={onPress}
      style={[s.choice, selected ? s.choiceOn : null, disabled ? s.choiceOff : null]}
    >
      <View style={[s.radio, selected ? s.radioOn : null]}>{selected ? <View style={s.radioDot} /> : null}</View>
      <View style={s.flex}>
        <Text variant="bodyStrong" tone={disabled ? 'fg3' : 'fg'}>
          {title}
        </Text>
        <Text variant="small" tone="fg3">
          {detail}
        </Text>
      </View>
    </Pressable>
  );
}

const useStyles = makeStyles((t) => ({
  flex: { flex: 1 },
  card: { gap: 12, paddingVertical: 14 },
  quick: { flexDirection: 'row', gap: 8 },
  chip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.pill, borderWidth: 1, borderColor: t.c.lineStrong },
  actions: { flexDirection: 'row', gap: 10 },
  choice: { flexDirection: 'row', gap: 12, padding: 12, borderRadius: radius.md, borderWidth: 1, borderColor: t.c.line },
  choiceOn: { borderColor: t.c.accent },
  choiceOff: { borderStyle: 'dashed', opacity: 0.7 },
  radio: { width: 18, height: 18, borderRadius: 9, borderWidth: 1.5, borderColor: t.c.lineStrong, alignItems: 'center', justifyContent: 'center', marginTop: 2 },
  radioOn: { borderColor: t.c.accent },
  radioDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: t.c.accent },
  barRow: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  barLabel: { width: 40 },
}));
