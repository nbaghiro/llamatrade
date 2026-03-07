/**
 * Monthly Returns Grid Component
 * Calendar-style grid showing monthly returns with color coding.
 */

import { useMemo } from 'react';

interface MonthlyReturnsGridProps {
  monthlyReturns: { [key: string]: number };
}

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function getReturnColor(value: number): string {
  // Color scale from red (negative) to green (positive)
  if (value <= -0.1) return 'bg-red-600 text-white';
  if (value <= -0.05) return 'bg-red-500 text-white';
  if (value <= -0.02) return 'bg-red-400 text-white';
  if (value < 0) return 'bg-red-200 dark:bg-red-900/50 text-red-800 dark:text-red-200';
  if (value === 0) return 'bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400';
  if (value <= 0.02) return 'bg-green-200 dark:bg-green-900/50 text-green-800 dark:text-green-200';
  if (value <= 0.05) return 'bg-green-400 text-white';
  if (value <= 0.1) return 'bg-green-500 text-white';
  return 'bg-green-600 text-white';
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

export default function MonthlyReturnsGrid({ monthlyReturns }: MonthlyReturnsGridProps) {
  // Process monthly returns into a grid by year
  const { years, grid, yearTotals, monthTotals } = useMemo(() => {
    const entries = Object.entries(monthlyReturns);
    if (entries.length === 0) {
      return { years: [], grid: {}, yearTotals: {}, monthTotals: {} };
    }

    // Parse all year-month keys
    const parsed = entries.map(([key, value]) => {
      const [year, month] = key.split('-').map(Number);
      return { year, month, value };
    });

    // Get unique years sorted
    const uniqueYears = Array.from(new Set(parsed.map((p) => p.year))).sort();

    // Build grid: year -> month -> value
    const gridData: Record<number, Record<number, number>> = {};
    for (const { year, month, value } of parsed) {
      if (!gridData[year]) gridData[year] = {};
      gridData[year][month] = value;
    }

    // Calculate year totals (sum of monthly returns)
    const yTotals: Record<number, number> = {};
    for (const year of uniqueYears) {
      yTotals[year] = Object.values(gridData[year] || {}).reduce((sum, v) => sum + v, 0);
    }

    // Calculate month averages across years
    const mTotals: Record<number, number> = {};
    for (let m = 1; m <= 12; m++) {
      const monthValues = uniqueYears
        .map((y) => gridData[y]?.[m])
        .filter((v): v is number => v !== undefined);
      if (monthValues.length > 0) {
        mTotals[m] = monthValues.reduce((sum, v) => sum + v, 0) / monthValues.length;
      }
    }

    return {
      years: uniqueYears,
      grid: gridData,
      yearTotals: yTotals,
      monthTotals: mTotals,
    };
  }, [monthlyReturns]);

  if (years.length === 0) {
    return (
      <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
        <div className="flex items-center justify-center h-32 text-gray-400 dark:text-gray-500">
          No monthly return data available
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white dark:bg-gray-900 rounded-xl border border-gray-200 dark:border-gray-800 p-6">
      <h3 className="font-medium text-gray-900 dark:text-gray-100 mb-4">Monthly Returns</h3>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr>
              <th className="text-left px-2 py-2 text-gray-500 dark:text-gray-400 font-medium">
                Year
              </th>
              {MONTHS.map((month) => (
                <th
                  key={month}
                  className="text-center px-2 py-2 text-gray-500 dark:text-gray-400 font-medium"
                >
                  {month}
                </th>
              ))}
              <th className="text-center px-2 py-2 text-gray-500 dark:text-gray-400 font-medium">
                Total
              </th>
            </tr>
          </thead>
          <tbody>
            {years.map((year) => (
              <tr key={year}>
                <td className="px-2 py-1 font-medium text-gray-900 dark:text-gray-100">{year}</td>
                {MONTHS.map((_, monthIdx) => {
                  const monthNum = monthIdx + 1;
                  const value = grid[year]?.[monthNum];
                  return (
                    <td key={monthIdx} className="px-1 py-1">
                      {value !== undefined ? (
                        <div
                          className={`px-2 py-1.5 text-center rounded font-mono text-xs ${getReturnColor(value)}`}
                          title={`${year}-${String(monthNum).padStart(2, '0')}: ${formatPercent(value)}`}
                        >
                          {formatPercent(value)}
                        </div>
                      ) : (
                        <div className="px-2 py-1.5 text-center text-gray-300 dark:text-gray-700">
                          -
                        </div>
                      )}
                    </td>
                  );
                })}
                <td className="px-1 py-1">
                  <div
                    className={`px-2 py-1.5 text-center rounded font-mono text-xs font-medium ${getReturnColor(yearTotals[year] || 0)}`}
                  >
                    {formatPercent(yearTotals[year] || 0)}
                  </div>
                </td>
              </tr>
            ))}

            {/* Average row */}
            {years.length > 1 && (
              <tr className="border-t border-gray-200 dark:border-gray-700">
                <td className="px-2 py-1 font-medium text-gray-500 dark:text-gray-400">Avg</td>
                {MONTHS.map((_, monthIdx) => {
                  const monthNum = monthIdx + 1;
                  const value = monthTotals[monthNum];
                  return (
                    <td key={monthIdx} className="px-1 py-1">
                      {value !== undefined ? (
                        <div
                          className={`px-2 py-1.5 text-center rounded font-mono text-xs ${getReturnColor(value)}`}
                        >
                          {formatPercent(value)}
                        </div>
                      ) : (
                        <div className="px-2 py-1.5 text-center text-gray-300 dark:text-gray-700">
                          -
                        </div>
                      )}
                    </td>
                  );
                })}
                <td className="px-1 py-1">
                  <div className="px-2 py-1.5 text-center text-gray-400 dark:text-gray-500">-</div>
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* Legend */}
      <div className="mt-4 flex items-center justify-center gap-4 text-xs text-gray-500 dark:text-gray-400">
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-4 rounded bg-red-500" />
          <span>Negative</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-4 rounded bg-gray-100 dark:bg-gray-800" />
          <span>Zero</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-4 h-4 rounded bg-green-500" />
          <span>Positive</span>
        </div>
      </div>
    </div>
  );
}
