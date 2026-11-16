import {
  formatMoney,
  formatNumber,
  formatPct,
  pnlTone,
  type FormatOptions,
} from '../../lib/format';

const TONE_CLASS = { gain: 'text-gain', loss: 'text-loss', flat: '' } as const;

interface FigureProps extends FormatOptions {
  value: number;
  /** Colour by sign. Only for profit and loss, never for prices, weights or counts. */
  pnl?: boolean;
  className?: string;
}

function toneClass(value: number, pnl: boolean, dp: number): string {
  return pnl ? TONE_CLASS[pnlTone(value, dp)] : '';
}

/** A plain figure in mono tabular digits. */
export function Num({ value, pnl = false, dp = 2, signed = pnl, className = '' }: FigureProps) {
  return (
    <span className={`num ${toneClass(value, pnl, dp)} ${className}`}>
      {formatNumber(value, { dp, signed })}
    </span>
  );
}

export function Money({ value, pnl = false, dp = 2, signed = pnl, className = '' }: FigureProps) {
  return (
    <span className={`num ${toneClass(value, pnl, dp)} ${className}`}>
      {formatMoney(value, { dp, signed })}
    </span>
  );
}

/** A percentage from a fraction: 0.0087 shows as 0.87%. */
export function Pct({ value, pnl = false, dp = 2, signed = pnl, className = '' }: FigureProps) {
  return (
    <span className={`num ${toneClass(value * 100, pnl, dp)} ${className}`}>
      {formatPct(value, { dp, signed })}
    </span>
  );
}
