import { formatPct } from '../../lib/format';

import { LineChart, type LineChartProps } from './LineChart';

interface DrawdownBandProps extends Pick<
  LineChartProps,
  'height' | 'xFormat' | 'pad' | 'className'
> {
  dates: readonly Date[];
  /** Fractional drawdown per point, 0 at a peak and negative below it. */
  drawdown: readonly number[];
  label?: string;
}

/** Drawdown under the zero line, filled in the loss colour. */
export function DrawdownBand({
  dates,
  drawdown,
  height = 120,
  label = 'Drawdown',
  ...rest
}: DrawdownBandProps) {
  return (
    <LineChart
      {...rest}
      label={label}
      dates={dates}
      height={height}
      yTickCount={2}
      series={[{ values: drawdown, kind: 'loss', area: true }]}
      base={0}
      ceil={0}
      zeroLine={0}
      yFormat={(v) => (v === 0 ? '0%' : formatPct(v, { dp: 0 }))}
      tooltip={(i) => (
        <>
          <b className="block font-medium text-fg-3">{dates[i]?.toISOString().slice(0, 10)}</b>
          Drawdown {formatPct(drawdown[i], { dp: 1 })}
        </>
      )}
    />
  );
}
