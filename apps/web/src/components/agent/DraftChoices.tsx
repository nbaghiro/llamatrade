import { useId, useState } from 'react';

import { presetPicks, type DraftPicks, type DraftQuestion } from './draftQuestions';

function Choice({
  question,
  value,
  onChange,
  disabled,
}: {
  question: DraftQuestion;
  value: string;
  onChange: (v: string) => void;
  disabled: boolean;
}) {
  const labelId = useId();
  return (
    <div className="grid gap-1.5 md:grid-cols-[230px_minmax(0,1fr)] md:items-start md:gap-4">
      <div id={labelId} className="min-w-0">
        <b className="block text-[13.5px] font-semibold md:text-[13px]">
          <span className="md:hidden">{question.short}</span>
          <span className="max-md:hidden">{question.label}</span>
        </b>
        {question.help && (
          <span className="block text-[12px] leading-[1.4] text-fg-3 max-md:hidden">
            {question.help}
          </span>
        )}
      </div>
      <div
        role="radiogroup"
        aria-labelledby={labelId}
        className="inline-flex max-w-full flex-wrap gap-0.5 justify-self-start rounded-[9px] bg-sunk p-[3px] max-md:rounded-full"
      >
        {question.options.map((o) => {
          const on = o === value;
          return (
            <button
              key={o}
              type="button"
              role="radio"
              aria-checked={on}
              disabled={disabled}
              onClick={() => onChange(o)}
              className={`whitespace-nowrap rounded-[7px] px-2.5 py-[5px] text-[12.5px] max-md:rounded-full max-md:px-3 ${
                on
                  ? 'bg-panel font-medium text-fg shadow-[0_1px_2px_rgb(0_0_0/0.12)]'
                  : 'text-fg-2 hover:text-fg disabled:hover:text-fg-2'
              }`}
            >
              {o}
            </button>
          );
        })}
      </div>
    </div>
  );
}

/**
 * The details that change how a drafted strategy would trade, each with Copilot's likely answer
 * selected (draft2 B). Shared by the Copilot thread and the builder's draft start.
 */
export function DraftChoices({
  questions,
  onDraft,
  onDefaults,
  onChange,
  disabled = false,
  answered = false,
}: {
  questions: readonly DraftQuestion[];
  onDraft: (picks: DraftPicks) => void;
  onDefaults: () => void;
  /** Each change of a choice, for a view that shows the picks elsewhere. */
  onChange?: (id: string, value: string) => void;
  disabled?: boolean;
  /** The person already replied; the card stays as a record. */
  answered?: boolean;
}) {
  const [picks, setPicks] = useState<DraftPicks>(() => presetPicks(questions));
  const locked = disabled || answered;
  return (
    <section
      aria-label="Choices before the draft"
      className={`overflow-hidden rounded-[12px] border bg-panel ${
        answered ? 'border-line' : 'border-accent/35 shadow-[0_0_0_3px_var(--accent-soft)]'
      }`}
    >
      <div className="grid gap-4 px-4 py-4 md:px-[18px]">
        {questions.map((q) => (
          <Choice
            key={q.id}
            question={q}
            value={picks[q.id] ?? q.preset}
            disabled={locked}
            onChange={(v) => {
              setPicks((p) => ({ ...p, [q.id]: v }));
              onChange?.(q.id, v);
            }}
          />
        ))}
      </div>
      <div className="flex flex-wrap items-center gap-2 border-t border-line bg-sunk/60 px-4 py-2.5 md:px-[18px]">
        {answered ? (
          <span className="text-[12px] text-fg-3">Answered below</span>
        ) : (
          <>
            <button
              type="button"
              className="btn btn-primary btn-sm max-md:w-full max-md:justify-center"
              disabled={locked}
              onClick={() => onDraft(picks)}
            >
              Draft with these
            </button>
            <button
              type="button"
              className="btn btn-ghost btn-sm"
              disabled={locked}
              onClick={onDefaults}
            >
              Just use your defaults
            </button>
            <span className="ml-auto text-[12px] text-fg-3">Nothing is saved or run yet</span>
          </>
        )}
      </div>
    </section>
  );
}
