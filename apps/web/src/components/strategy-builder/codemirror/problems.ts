// Engine problems drawn as cards under their line, with one-click fixes where the engine offers them.

import { StateEffect, StateField, type EditorState, type Range } from '@codemirror/state';
import { Decoration, EditorView, WidgetType, type DecorationSet } from '@codemirror/view';

import type { CodeProblem } from './problemModel';

export const setProblems = StateEffect.define<readonly CodeProblem[]>();

/** Cards past this many show their title only, so several problems don't push the code apart. */
const OPEN_CARDS = 2;

class ProblemWidget extends WidgetType {
  constructor(
    readonly problem: CodeProblem,
    readonly open: boolean
  ) {
    super();
  }

  eq(other: ProblemWidget): boolean {
    return (
      other.open === this.open &&
      other.problem.title === this.problem.title &&
      other.problem.line === this.problem.line &&
      other.problem.choices.length === this.problem.choices.length &&
      other.problem.choices.every((c, i) => c.from === this.problem.choices[i].from)
    );
  }

  toDOM(view: EditorView): HTMLElement {
    const wrap = document.createElement('div');
    wrap.className = 'cm-problem';
    const card = document.createElement('div');
    card.className = 'cm-problem-card';
    card.setAttribute('role', 'note');
    const head = document.createElement('div');
    head.className = 'cm-problem-head';
    const title = document.createElement('b');
    title.textContent = this.problem.title;
    head.append(title);
    if (this.problem.line > 0) {
      const where = document.createElement('span');
      where.textContent = `Line ${this.problem.line}`;
      head.append(where);
    }
    card.append(head);
    if (this.open && this.problem.body) {
      const body = document.createElement('p');
      body.textContent = this.problem.body;
      card.append(body);
    }
    if (this.open && this.problem.choices.length) {
      const row = document.createElement('div');
      row.className = 'cm-problem-choices';
      for (const choice of this.problem.choices) {
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.textContent = choice.label;
        btn.addEventListener('mousedown', (e) => e.preventDefault());
        btn.addEventListener('click', () => {
          view.dispatch({ changes: { from: choice.from, to: choice.to, insert: choice.insert } });
          view.focus();
        });
        row.append(btn);
      }
      card.append(row);
    }
    wrap.append(card);
    return wrap;
  }

  ignoreEvent(): boolean {
    return true;
  }
}

const problemLine = Decoration.line({ class: 'cm-problem-line' });
const problemMark = Decoration.mark({ class: 'cm-problem-mark' });

function build(state: EditorState, problems: readonly CodeProblem[]): DecorationSet {
  const ranges: Range<Decoration>[] = [];
  const docLen = state.doc.length;
  problems.forEach((p, i) => {
    const open = i < OPEN_CARDS;
    if (p.line < 1 || p.line > state.doc.lines) {
      ranges.push(
        Decoration.widget({ widget: new ProblemWidget(p, open), block: true, side: -1 }).range(0)
      );
      return;
    }
    const line = state.doc.line(p.line);
    ranges.push(problemLine.range(line.from));
    if (p.mark && p.mark.from < p.mark.to && p.mark.to <= docLen) {
      ranges.push(problemMark.range(p.mark.from, p.mark.to));
    }
    ranges.push(
      Decoration.widget({ widget: new ProblemWidget(p, open), block: true, side: 1 }).range(line.to)
    );
  });
  return Decoration.set(ranges, true);
}

export const problemsField = StateField.define<DecorationSet>({
  create: () => Decoration.none,
  update(value, tr) {
    let next = value.map(tr.changes);
    for (const e of tr.effects) if (e.is(setProblems)) next = build(tr.state, e.value);
    return next;
  },
  provide: (f) => EditorView.decorations.from(f),
});

export const problemsTheme = EditorView.baseTheme({
  '.cm-problem-line': {
    backgroundColor: 'var(--risk-soft)',
    boxShadow: 'inset 2px 0 0 rgb(var(--risk))',
  },
  '.cm-problem-mark': {
    textDecoration: 'underline wavy rgb(var(--risk))',
    textUnderlineOffset: '4px',
  },
  '.cm-problem': {
    padding: '4px 16px 10px 16px',
    fontFamily: 'var(--font-sans)',
    whiteSpace: 'normal',
  },
  '.cm-problem-card': {
    border: '1px solid var(--risk-line)',
    borderRadius: 'var(--radius-panel)',
    background: 'rgb(var(--panel))',
    padding: '12px 14px',
    display: 'grid',
    gap: '10px',
    fontSize: '12.5px',
    lineHeight: '1.5',
    maxWidth: '600px',
  },
  '.cm-problem-head': { display: 'flex', justifyContent: 'space-between', gap: '12px' },
  '.cm-problem-head b': { color: 'rgb(var(--risk))', fontWeight: '600' },
  '.cm-problem-head span': { color: 'rgb(var(--fg-3))', fontSize: '11.5px' },
  '.cm-problem-card p': { margin: '0', color: 'rgb(var(--fg-2))' },
  '.cm-problem-choices': { display: 'flex', gap: '6px', flexWrap: 'wrap' },
  '.cm-problem-choices button': {
    font: '500 11.5px var(--font-mono)',
    padding: '4px 8px',
    borderRadius: 'var(--radius)',
    boxShadow: 'inset 0 0 0 1px rgb(var(--line-strong))',
    color: 'rgb(var(--fg))',
    background: 'transparent',
    cursor: 'pointer',
  },
  '.cm-problem-choices button:hover': {
    boxShadow: 'inset 0 0 0 1px rgb(var(--accent)), 0 0 0 3px var(--accent-soft)',
    color: 'rgb(var(--accent))',
  },
});
