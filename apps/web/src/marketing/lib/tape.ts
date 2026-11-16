/** Splits "(sma SPY 200)" into the opening paren, the operator and the rest. */
export function splitRule(rule: string): [string, string, string] {
  const m = /^\(([a-z-]+)(.*)$/.exec(rule);
  return m ? ['(', m[1], m[2]] : ['', '', rule];
}
