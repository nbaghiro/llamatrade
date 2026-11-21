import { Minus, Plus } from 'lucide-react-native';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, View, type LayoutChangeEvent } from 'react-native';
import Svg, { Line, Path, Rect, Text as SvgText } from 'react-native-svg';

import { loadDailyCloses } from '../backtests/bars';
import type { Point } from '../backtests/model';
import { linePath, rangeOf, yFor } from '../charts/paths';
import { fonts, makeStyles, radius, useTheme } from '../theme';
import { Button, Segmented, Text } from '../ui';
import { indicatorSeries, thresholdCounts } from './indicators';
import { formatValue, stepValue, type EditableValue } from './sentences';
import { Sheet } from './Sheet';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
const monthYear = (t: number) => `${MON[new Date(t).getUTCMonth()]} ${new Date(t).getUTCFullYear()}`;
const HISTORY_DAYS = 730;

type History = { status: 'loading' } | { status: 'none' } | { status: 'error' } | { status: 'ready'; points: Point[]; series: number[] };

/** The indicator's last two years from daily closes, when the builder knows how to compute it. */
function useHistory(value: EditableValue | null): History {
  const [state, setState] = useState<History>({ status: 'none' });
  const ref = value?.against ?? null;
  const key = ref ? `${ref.name}:${ref.symbol}:${ref.period ?? ''}` : '';
  useEffect(() => {
    if (!ref || !ref.symbol || indicatorSeries(ref.name, [1, 2], ref.period) === null) {
      setState({ status: 'none' });
      return;
    }
    let live = true;
    setState({ status: 'loading' });
    const end = Date.now();
    const warm = (ref.period ?? 14) * 2 * 86_400_000;
    loadDailyCloses(ref.symbol, end - HISTORY_DAYS * 86_400_000 - warm, end)
      .then((bars) => {
        if (!live) return;
        const raw = indicatorSeries(ref.name, bars.map((b) => b.value), ref.period) ?? [];
        const from = end - HISTORY_DAYS * 86_400_000;
        const points: Point[] = [];
        const series: number[] = [];
        raw.forEach((v, i) => {
          if (v !== null && bars[i].at >= from) {
            points.push(bars[i]);
            series.push(v);
          }
        });
        setState(series.length > 10 ? { status: 'ready', points, series } : { status: 'error' });
      })
      .catch(() => live && setState({ status: 'error' }));
    return () => {
      live = false;
    };
    // `ref` is identified by `key`.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);
  return state;
}

function ThresholdChart({ series, threshold, was }: { series: number[]; threshold: number; was: number }) {
  const { c } = useTheme();
  const [w, setW] = useState(0);
  const h = 96;
  const range = rangeOf(series, [threshold, was]);
  const onLayout = (e: LayoutChangeEvent) => setW(Math.round(e.nativeEvent.layout.width));
  const ty = range ? yFor(threshold, range, h, 6) : 0;
  const wy = range ? yFor(was, range, h, 6) : 0;
  const label = String(threshold);
  return (
    <View onLayout={onLayout} style={{ height: h }}>
      {w > 0 && range ? (
        <Svg width={w} height={h}>
          <Path d={linePath(series, w, h, 6, range)} fill="none" stroke={c.accent} strokeWidth={1.4} strokeLinejoin="round" />
          {was !== threshold ? <Line x1={0} x2={w} y1={wy} y2={wy} stroke={c.fg3} strokeWidth={1} strokeDasharray="3 3" /> : null}
          <Line x1={0} x2={w} y1={ty} y2={ty} stroke={c.fg} strokeWidth={1.2} />
          <Rect x={w - 8 - label.length * 7.5 - 8} y={ty - 9} width={label.length * 7.5 + 8} height={16} rx={3} fill={c.fg} />
          <SvgText x={w - 12} y={ty + 3.5} fill={c.canvas} fontSize={11} fontFamily={fonts.monoMedium} textAnchor="end">{label}</SvgText>
        </Svg>
      ) : null}
    </View>
  );
}

/**
 * The sheet for one value: a stepper (or choices for the cadence), the value's history with the
 * threshold across it where the indicator can be computed, and the save.
 */
export function ValueSheet({
  value,
  saved,
  onClose,
  onSave,
  saveLabel,
  saving,
}: {
  value: EditableValue | null;
  /** The value's text in the saved version, for "was". */
  saved: string | null;
  onClose: () => void;
  onSave: (text: string) => void;
  saveLabel: string;
  saving: boolean;
}) {
  const s = useStyles();
  const { c } = useTheme();
  const [text, setText] = useState(value?.text ?? '');
  useEffect(() => setText(value?.text ?? ''), [value]);
  const history = useHistory(value);
  const n = Number(text);
  const counts = useMemo(() => (history.status === 'ready' && Number.isFinite(n) ? thresholdCounts(history.series, n) : null), [history, n]);
  if (!value) return <Sheet visible={false} onClose={onClose}>{null}</Sheet>;
  const ref = value.against;
  const step = (dir: 1 | -1) => setText(formatValue(stepValue(value, Number(text), dir), value.step));
  return (
    <Sheet visible onClose={onClose}>
      <View style={s.head}>
        <Text variant="subhead">{value.label}</Text>
        {saved !== null && saved !== text ? <Text variant="numSmall" tone="fg3">was {saved}</Text> : null}
      </View>

      {value.kind === 'choice' ? (
        <Segmented options={value.choices.map((ch) => ({ key: ch, label: ch.charAt(0).toUpperCase() + ch.slice(1) }))} value={text} onChange={setText} />
      ) : (
        <View style={s.stepper}>
          <Pressable accessibilityRole="button" accessibilityLabel="Decrease" onPress={() => step(-1)} style={s.stepBtn} hitSlop={6}>
            <Minus color={c.fg2} size={18} strokeWidth={1.8} />
          </Pressable>
          <Text variant="hero" style={s.stepValue}>{text}{value.suffix === '%' ? '%' : ''}</Text>
          <Pressable accessibilityRole="button" accessibilityLabel="Increase" onPress={() => step(1)} style={s.stepBtn} hitSlop={6}>
            <Plus color={c.fg2} size={18} strokeWidth={1.8} />
          </Pressable>
        </View>
      )}

      {ref && history.status === 'ready' ? (
        <View style={s.history}>
          <ThresholdChart series={history.series} threshold={n} was={Number(saved ?? text)} />
          <View style={s.caption}>
            <Text variant="caption" tone="fg3" style={s.flex}>
              {ref.symbol}'s {ref.period ? `${ref.period}-day ` : ''}{ref.name.toUpperCase()}, {monthYear(history.points[0].at)} to {monthYear(history.points[history.points.length - 1].at)}
            </Text>
            {saved !== null && saved !== text ? <Text variant="caption" tone="fg3">dashed {saved}</Text> : null}
          </View>
          {counts ? (
            <Text variant="small" tone="fg2">
              Above {text} on {counts.above} of {counts.days} trading days, crossing up {counts.crossings} {counts.crossings === 1 ? 'time' : 'times'}.
            </Text>
          ) : null}
        </View>
      ) : ref && history.status === 'loading' ? (
        <Text variant="small" tone="fg3">Loading {ref.symbol}'s history</Text>
      ) : ref && history.status === 'error' ? (
        <Text variant="small" tone="fg3">{ref.symbol}'s history could not be loaded, so the chart is left out.</Text>
      ) : null}

      <View style={s.buttons}>
        <Button label="Cancel" variant="secondary" onPress={onClose} style={s.flex} />
        <Button label={saveLabel} onPress={() => onSave(text)} loading={saving} disabled={text === value.text} style={s.flex} />
      </View>
    </Sheet>
  );
}

const useStyles = makeStyles((t) => ({
  head: { flexDirection: 'row', alignItems: 'baseline', justifyContent: 'space-between' },
  stepper: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  stepBtn: { width: 44, height: 44, borderRadius: radius.md, backgroundColor: t.c.sunk, alignItems: 'center', justifyContent: 'center' },
  stepValue: { textAlign: 'center', flex: 1 },
  history: { gap: 6 },
  caption: { flexDirection: 'row', justifyContent: 'space-between', gap: 8 },
  flex: { flex: 1 },
  buttons: { flexDirection: 'row', gap: 10, marginTop: 4 },
}));
