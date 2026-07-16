/**
 * Monthly Returns heatmap.
 * Year-by-month grid with a green→red diverging fill keyed off return sign and
 * magnitude, plus a compounded annual total column.
 */

import { useMemo } from 'react';

interface MonthlyReturnsGridProps {
  monthlyReturns: { [key: string]: number };
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

// Diverging fill: alpha scales with magnitude, saturating at ±5%.
function cellStyle(value: number | undefined): React.CSSProperties {
  if (value === undefined) return { background: 'rgb(var(--lt-bone))', color: 'rgba(13,13,13,.25)' };
  const pct = value * 100;
  const a = 0.15 + 0.7 * Math.min(Math.abs(pct) / 5, 1);
  const rgb = value >= 0 ? '15,122,52' : '200,30,30';
  return { background: `rgba(${rgb},${a.toFixed(2)})`, color: a > 0.5 ? 'rgb(var(--lt-bone))' : '#0d0d0d' };
}

function signedPercent(pct: number, digits = 1): string {
  return `${pct >= 0 ? '+' : ''}${pct.toFixed(digits)}`;
}

export default function MonthlyReturnsGrid({ monthlyReturns }: MonthlyReturnsGridProps) {
  const { years, grid, yearTotals, best, worst, hasData } = useMemo(() => {
    const parsed = Object.entries(monthlyReturns)
      .map(([key, value]) => {
        const [year, month] = key.split('-').map(Number);
        return { year, month, value };
      })
      .filter((p) => Number.isFinite(p.year) && p.month >= 1 && p.month <= 12);

    const uniqueYears = Array.from(new Set(parsed.map((p) => p.year))).sort((a, b) => a - b);
    const gridData: Record<number, Record<number, number>> = {};
    for (const { year, month, value } of parsed) {
      (gridData[year] ??= {})[month] = value;
    }

    // Compounded annual return from the months present.
    const totals: Record<number, number> = {};
    for (const year of uniqueYears) {
      const months = Object.values(gridData[year]);
      totals[year] = months.reduce((acc, v) => acc * (1 + v), 1) - 1;
    }

    const values = parsed.map((p) => p.value);
    return {
      years: uniqueYears,
      grid: gridData,
      yearTotals: totals,
      best: values.length ? Math.max(...values) : 0,
      worst: values.length ? Math.min(...values) : 0,
      hasData: parsed.length > 0,
    };
  }, [monthlyReturns]);

  return (
    <div className="bg-paper border-2 border-ink shadow-[4px_4px_0_#0d0d0d]">
      <div className="flex items-center justify-between px-4 py-3 border-b-2 border-ink">
        <span className="font-mono text-[11px] font-bold uppercase tracking-[0.1em]">Monthly Returns</span>
        {hasData && (
          <span className="font-mono text-[10px] font-bold uppercase tracking-[0.04em] border-[1.5px] border-ink px-1.5 py-[3px]">
            Best {signedPercent(best * 100)}% · Worst {signedPercent(worst * 100)}%
          </span>
        )}
      </div>

      {!hasData ? (
        <div className="px-4 py-8 font-mono text-[11px] uppercase tracking-[0.05em] text-ink/40 text-center">
          No monthly return data
        </div>
      ) : (
        <div className="px-4 pt-3.5 pb-4 overflow-x-auto">
          <table className="w-full border-collapse tabular-nums">
            <thead>
              <tr>
                <th className="text-left pl-0.5 pb-2 pt-1 font-mono text-[9.5px] font-bold uppercase tracking-[0.04em] text-ink/55">
                  Year
                </th>
                {MONTHS.map((m) => (
                  <th
                    key={m}
                    className="text-center pb-2 pt-1 font-mono text-[9.5px] font-bold uppercase tracking-[0.04em] text-ink/55"
                  >
                    {m}
                  </th>
                ))}
                <th className="text-center pb-2 pt-1 font-mono text-[9.5px] font-bold uppercase tracking-[0.04em] text-ink/55">
                  Year
                </th>
              </tr>
            </thead>
            <tbody>
              {years.map((year) => (
                <tr key={year}>
                  <td className="text-left pr-2 font-mono font-bold text-[12px]">{year}</td>
                  {MONTHS.map((_, idx) => {
                    const value = grid[year]?.[idx + 1];
                    return (
                      <td
                        key={idx}
                        className="text-center border-[1.5px] border-ink font-mono text-[11px] font-bold h-[30px] w-[6.7%]"
                        style={cellStyle(value)}
                        title={value !== undefined ? `${year}-${String(idx + 1).padStart(2, '0')}: ${signedPercent(value * 100)}%` : undefined}
                      >
                        {value !== undefined ? signedPercent(value * 100) : '·'}
                      </td>
                    );
                  })}
                  <td className="text-center border-2 border-ink bg-ink text-bone font-mono text-[11px] font-bold h-[30px]">
                    {signedPercent(yearTotals[year] * 100)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>

          <div className="flex items-center gap-2 mt-3 font-mono text-[9.5px] font-bold uppercase tracking-[0.05em] text-ink/50">
            <span>−5%</span>
            <span className="flex h-3 w-[190px] border-2 border-ink">
              <span className="flex-1" style={{ background: 'rgba(200,30,30,.85)' }} />
              <span className="flex-1" style={{ background: 'rgba(200,30,30,.4)' }} />
              <span className="flex-1 bg-bone" />
              <span className="flex-1" style={{ background: 'rgba(15,122,52,.4)' }} />
              <span className="flex-1" style={{ background: 'rgba(15,122,52,.85)' }} />
            </span>
            <span>+5%</span>
          </div>
        </div>
      )}
    </div>
  );
}
