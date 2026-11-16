import { AlertTriangle, CheckCircle2, Info, Link2 } from 'lucide-react';
import type { InputHTMLAttributes, ReactNode } from 'react';

interface FieldProps extends InputHTMLAttributes<HTMLInputElement> {
  id: string;
  label: string;
  /** Shown at the right of the label, e.g. "Forgot password?"; it follows the input in tab order. */
  aside?: ReactNode;
  help?: ReactNode;
}

export function Field({ id, label, aside, help, className = '', ...input }: FieldProps) {
  const helpId = help ? `${id}-help` : undefined;
  return (
    <div className="relative grid gap-1.5">
      <label htmlFor={id} className="text-[12px] font-medium text-fg-2">
        {label}
      </label>
      <input id={id} aria-describedby={helpId} className={`input ${className}`} {...input} />
      {aside && <div className="absolute right-0 top-0 text-[12px] font-medium">{aside}</div>}
      {help && (
        <span id={helpId} className="text-[11.5px] text-fg-3">
          {help}
        </span>
      )}
    </div>
  );
}

export type NoteTone = 'info' | 'ok' | 'warn';

const NOTE_TONE: Record<NoteTone, { box: string; icon: string; Icon: typeof Info }> = {
  info: { box: 'border-line-strong bg-sunk', icon: 'text-fg-2', Icon: Info },
  ok: { box: 'border-line-strong bg-sunk', icon: 'text-accent', Icon: CheckCircle2 },
  warn: { box: 'border-risk-line bg-risk-soft', icon: 'text-risk', Icon: AlertTriangle },
};

/** A one-line note inside a form. Warn is for errors and things that need attention. */
export function FormNote({ tone = 'info', children }: { tone?: NoteTone; children: ReactNode }) {
  const t = NOTE_TONE[tone];
  return (
    <div
      role={tone === 'warn' ? 'alert' : 'status'}
      className={`flex items-center gap-2.5 rounded-[8px] border px-3 py-2.5 text-[12.5px] text-fg-2 [&_b]:font-semibold [&_b]:text-fg ${t.box}`}
    >
      <t.Icon aria-hidden="true" className={`h-4 w-4 flex-none ${t.icon}`} />
      <span className="min-w-0 flex-1">{children}</span>
    </div>
  );
}

export function OrDivider() {
  return (
    <div
      aria-hidden="true"
      className="flex items-center gap-2.5 text-[11.5px] text-fg-3 before:h-px before:flex-1 before:bg-line after:h-px after:flex-1 after:bg-line"
    >
      or
    </div>
  );
}

export function AlpacaButton({
  label,
  onClick,
  disabled,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      className="btn btn-secondary btn-lg w-full"
      onClick={onClick}
      disabled={disabled}
    >
      <Link2 aria-hidden="true" className="h-4 w-4" />
      {label}
    </button>
  );
}

/** The quiet line under a form: "New to LlamaTrade? Create an account". */
export function FormFoot({ children }: { children: ReactNode }) {
  return <p className="m-0 text-center text-[12.5px] text-fg-3">{children}</p>;
}

export const LINK = 'text-accent hover:underline underline-offset-2';
