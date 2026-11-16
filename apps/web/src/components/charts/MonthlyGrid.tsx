import {
  cellAlpha,
  cellText,
  cellTextShort,
  FLAT_RETURN,
  monthlyRows,
} from '../../lib/chart/monthly';
import { formatPct } from '../../lib/format';
import type { MonthReturn } from '../../lib/illustrative/series';

const MON = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

interface MonthlyGridProps {
  months: readonly MonthReturn[];
  /** Highlights one cell, e.g. "2025-3" for April 2025. */
  selected?: string;
  className?: string;
}

function cellBackground(r: number): string {
  if (Math.abs(r) < FLAT_RETURN) return 'rgb(var(--sunk))';
  return `rgb(var(--${r >= 0 ? 'gain' : 'loss'}) / ${cellAlpha(r).toFixed(3)})`;
}

/** Monthly returns: rows by year, January to December, shaded by size. */
export function MonthlyGrid({ months, selected, className = '' }: MonthlyGridProps) {
  const rows = monthlyRows(months);
  return (
    <table
      className={`w-full border-separate border-spacing-px font-mono text-[9.5px] tabular-nums sm:border-spacing-0.5 sm:text-[10.5px] ${className}`}
    >
      <thead>
        <tr>
          <th />
          {MON.map((m) => (
            <th
              key={m}
              scope="col"
              className="px-px py-[3px] text-center font-sans text-[10px] font-medium text-fg-3"
            >
              {m[0]}
              <span className="hidden sm:inline">{m.slice(1)}</span>
            </th>
          ))}
          <th
            scope="col"
            className="py-[3px] pl-1 text-right font-sans text-[10px] font-medium text-fg-3 sm:pl-1.5"
          >
            Year
          </th>
        </tr>
      </thead>
      <tbody>
        {rows.map((row) => (
          <tr key={row.year}>
            <th scope="row" className="pr-1 text-left font-medium text-fg-3">
              {row.year}
            </th>
            {row.cells.map((c) =>
              c.r === null ? (
                <td key={c.m} />
              ) : (
                <td
                  key={c.m}
                  title={`${MON[c.m]} ${row.year}: ${formatPct(c.r, { dp: 1, signed: true })}`}
                  className={`rounded-[1px] py-[5px] text-center text-fg ${
                    selected === `${row.year}-${c.m}` ? 'outline outline-1 outline-accent' : ''
                  }`}
                  style={{ background: cellBackground(c.r) }}
                >
                  <span className="sm:hidden">{cellTextShort(c.r)}</span>
                  <span className="hidden sm:inline">{cellText(c.r)}</span>
                </td>
              )
            )}
            <td className="pl-1 text-right text-fg-2 sm:pl-1.5">
              {formatPct(row.total, { dp: 1, signed: true })}
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
