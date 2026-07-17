// Real-time linting for the strategy DSL editor

import { linter, type Diagnostic } from '@codemirror/lint';
import type { EditorView } from '@codemirror/view';
import { tokenizeWithPositions, type TokenWithPosition } from '@llamatrade/core/strategy/serializer';

const VALID_WEIGHT_METHODS = new Set([
  'equal', 'specified', 'momentum', 'inverse-volatility', 'min-variance', 'risk-parity',
  'inverse_volatility', 'min_variance', 'risk_parity',
]);

const VALID_SELECTIONS = new Set(['top', 'bottom']);

/**
 * Check for balanced brackets
 */
function checkBrackets(tokens: TokenWithPosition[]): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const stack: { char: string; token: TokenWithPosition }[] = [];
  const pairs: Record<string, string> = { '(': ')', '[': ']', '{': '}' };
  const closers: Record<string, string> = { ')': '(', ']': '[', '}': '{' };

  for (const token of tokens) {
    if (token.type === 'bracket') {
      if (pairs[token.value]) {
        stack.push({ char: token.value, token });
      } else if (closers[token.value]) {
        const last = stack.pop();
        if (!last || last.char !== closers[token.value]) {
          diagnostics.push({
            from: token.start,
            to: token.end,
            severity: 'error',
            message: `Unmatched closing bracket '${token.value}'`,
          });
        }
      }
    }
  }

  // Report unclosed brackets
  for (const item of stack) {
    diagnostics.push({
      from: item.token.start,
      to: item.token.end,
      severity: 'error',
      message: `Unclosed bracket '${item.char}'`,
    });
  }

  return diagnostics;
}

/**
 * Check for unclosed strings
 */
function checkStrings(_code: string, tokens: TokenWithPosition[]): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];

  for (const token of tokens) {
    if (token.type === 'string') {
      // Check if string is properly closed
      if (!token.value.endsWith('"') || token.value.length < 2) {
        diagnostics.push({
          from: token.start,
          to: token.end,
          severity: 'error',
          message: 'Unclosed string literal',
        });
      }
    }
  }

  return diagnostics;
}

/**
 * Check for invalid weight methods
 */
function checkWeightMethods(tokens: TokenWithPosition[]): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];

    // Check for :method followed by invalid value
    if (token.type === 'parameter' && token.value === ':method') {
      const next = tokens[i + 1];
      if (next && next.type !== 'bracket') {
        if (!VALID_WEIGHT_METHODS.has(next.value.toLowerCase())) {
          diagnostics.push({
            from: next.start,
            to: next.end,
            severity: 'error',
            message: `Invalid weight method '${next.value}'. Valid methods: equal, specified, momentum, inverse-volatility, min-variance, risk-parity`,
          });
        }
      }
    }

    // Check for :selection followed by invalid value
    if (token.type === 'parameter' && token.value === ':selection') {
      const next = tokens[i + 1];
      if (next && next.type !== 'bracket') {
        if (!VALID_SELECTIONS.has(next.value.toLowerCase())) {
          diagnostics.push({
            from: next.start,
            to: next.end,
            severity: 'error',
            message: `Invalid selection '${next.value}'. Valid values: top, bottom`,
          });
        }
      }
    }
  }

  return diagnostics;
}

/**
 * Check for negative counts
 */
function checkCounts(tokens: TokenWithPosition[]): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];

    if (token.type === 'parameter' && token.value === ':count') {
      const next = tokens[i + 1];
      if (next && next.type === 'number') {
        const value = parseFloat(next.value);
        if (value < 1) {
          diagnostics.push({
            from: next.start,
            to: next.end,
            severity: 'error',
            message: 'Count must be at least 1',
          });
        }
      }
    }
  }

  return diagnostics;
}

/**
 * Check for weight percentages outside the valid 0–100 range. Weights are
 * percents (sibling weights sum to 100), not 0–1 fractions.
 */
function checkWeights(tokens: TokenWithPosition[]): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];

    if (token.type === 'parameter' && token.value === ':weight') {
      const next = tokens[i + 1];
      if (next && next.type === 'number') {
        const value = parseFloat(next.value);
        if (value < 0 || value > 100) {
          diagnostics.push({
            from: next.start,
            to: next.end,
            severity: 'warning',
            message: 'Weight is a percent from 0 to 100 (sibling weights should sum to 100).',
          });
        }
      }
    }
  }

  return diagnostics;
}

const WEIGHT_SUM_TARGET = 100;
const WEIGHT_SUM_TOLERANCE = 0.5; // allow decimal rounding (e.g. 33.3 × 3 = 99.9)

interface WeightScope {
  head: string | null;
  isSpecified: boolean;
  anchor: TokenWithPosition | null;
  sum: number;
  count: number;
  awaitingHead: boolean;
}

/**
 * Check that each `(weight :method specified …)` block's direct child weights
 * sum to 100. Weights are percents, so a specified block must total 100. Blocks
 * with a computed method (equal/momentum/…) are skipped; blocks are only checked
 * on their closing paren (an unclosed block mid-edit is left alone), and only
 * once they carry ≥1 explicit child weight (avoids flagging a half-typed block).
 */
export function checkWeightSums(tokens: TokenWithPosition[]): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];
  const stack: WeightScope[] = [];

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];

    if (token.type === 'bracket') {
      if (token.value === '(') {
        stack.push({ head: null, isSpecified: false, anchor: null, sum: 0, count: 0, awaitingHead: true });
      } else if (token.value === ')') {
        const scope = stack.pop();
        if (
          scope &&
          scope.isSpecified &&
          scope.count >= 1 &&
          Math.abs(scope.sum - WEIGHT_SUM_TARGET) > WEIGHT_SUM_TOLERANCE
        ) {
          const total = parseFloat(scope.sum.toFixed(2));
          const anchor = scope.anchor ?? token;
          diagnostics.push({
            from: anchor.start,
            to: anchor.end,
            severity: 'warning',
            message: `Specified weights sum to ${total}, not 100 — adjust the ${scope.count} weights to total 100.`,
          });
        }
      }
      continue;
    }

    const scope = stack[stack.length - 1];
    if (!scope) continue;

    // First non-bracket token in a list is its head keyword.
    if (scope.awaitingHead) {
      scope.awaitingHead = false;
      scope.head = token.type === 'keyword' ? token.value.toLowerCase() : null;
      if (scope.head === 'weight') scope.anchor = token;
    }

    // `(weight :method specified …)` → this block must total 100.
    if (token.type === 'parameter' && token.value === ':method' && scope.head === 'weight') {
      const next = tokens[i + 1];
      if (next && next.value.toLowerCase() === 'specified') scope.isSpecified = true;
    }

    // A child's `:weight <num>` counts toward its PARENT specified block.
    if (token.type === 'parameter' && token.value === ':weight') {
      const next = tokens[i + 1];
      const parent = stack[stack.length - 2];
      if (next && next.type === 'number' && parent && parent.isSpecified) {
        const value = parseFloat(next.value);
        if (!Number.isNaN(value)) {
          parent.sum += value;
          parent.count += 1;
        }
      }
    }
  }

  return diagnostics;
}

/**
 * Check for empty symbol strings
 */
function checkSymbols(tokens: TokenWithPosition[]): Diagnostic[] {
  const diagnostics: Diagnostic[] = [];

  for (let i = 0; i < tokens.length; i++) {
    const token = tokens[i];

    if (token.type === 'parameter' && token.value === ':symbol') {
      const next = tokens[i + 1];
      if (next && next.type === 'string') {
        const value = next.value.slice(1, -1); // Remove quotes
        if (!value || value.trim() === '') {
          diagnostics.push({
            from: next.start,
            to: next.end,
            severity: 'error',
            message: 'Symbol cannot be empty',
          });
        }
      }
    }
  }

  return diagnostics;
}

/**
 * Main linting function
 */
function lintDSL(view: EditorView): Diagnostic[] {
  const code = view.state.doc.toString();

  // Return early for empty documents
  if (!code.trim()) {
    return [];
  }

  const tokens = tokenizeWithPositions(code);
  const diagnostics: Diagnostic[] = [];

  // Run all checks
  diagnostics.push(...checkBrackets(tokens));
  diagnostics.push(...checkStrings(code, tokens));
  diagnostics.push(...checkWeightMethods(tokens));
  diagnostics.push(...checkCounts(tokens));
  diagnostics.push(...checkWeights(tokens));
  diagnostics.push(...checkWeightSums(tokens));
  diagnostics.push(...checkSymbols(tokens));

  return diagnostics;
}

/**
 * CodeMirror linter extension for the strategy DSL
 */
export const dslLinter = linter(lintDSL, {
  delay: 300, // Throttle linting to avoid too frequent updates
});

export { lintDSL };
