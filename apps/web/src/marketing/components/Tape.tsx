import { MARKETING_TAPE, TAPE_ITEMS } from '../../config/marketing';
import { splitRule } from '../lib/tape';

/** Funds the strategy language trades, each with its name and a rule written for it. No prices. */
export function Tape() {
  if (MARKETING_TAPE === 'off') return null;
  const run = [...TAPE_ITEMS, ...TAPE_ITEMS];
  return (
    <div className="tape">
      <div className="tape-run" aria-hidden="true">
        <div className="tape-in">
          {run.map((item, i) => {
            const [open, op, rest] = splitRule(item.rule);
            return (
              <span key={i} className="q">
                <b>{item.symbol}</b>
                <span className="nm">{item.name}</span>
                <code>
                  {open}
                  <i>{op}</i>
                  {rest}
                </code>
              </span>
            );
          })}
        </div>
      </div>
      <span className="sr-only">
        Funds you can trade, with example rules:{' '}
        {TAPE_ITEMS.map((t) => `${t.symbol} (${t.name}) ${t.rule}`).join(', ')}.
      </span>
    </div>
  );
}
