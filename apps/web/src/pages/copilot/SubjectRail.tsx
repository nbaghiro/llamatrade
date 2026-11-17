import { CircleDot, History, LineChart, Layers, PieChart } from 'lucide-react';

import {
  ACCOUNT_SUBJECT,
  type CopilotSubject,
  type SubjectGroups,
} from '../../components/agent/subjects';

const DOT: Record<CopilotSubject['tone'], string> = {
  accent: 'bg-accent',
  risk: 'bg-risk',
  muted: 'bg-fg-3 rounded-[2px]',
  none: 'bg-transparent',
};

function Row({
  subject,
  selected,
  onSelect,
  icon,
}: {
  subject: CopilotSubject;
  selected: boolean;
  onSelect: (s: CopilotSubject) => void;
  icon?: React.ReactNode;
}) {
  return (
    <button
      type="button"
      onClick={() => onSelect(subject)}
      aria-current={selected ? 'true' : undefined}
      className={`flex w-full items-center gap-3 border-l-2 py-2 pl-[18px] pr-[18px] text-left text-[13.5px] ${
        selected ? 'border-accent bg-sunk' : 'border-transparent hover:bg-sunk/60'
      }`}
    >
      {icon ?? (
        <span aria-hidden className={`h-2 w-2 flex-none rounded-full ${DOT[subject.tone]}`} />
      )}
      <span className="min-w-0 flex-1 text-fg">{subject.name}</span>
      {subject.meta && (
        <span
          className={`flex-none font-mono text-[12px] ${subject.tone === 'risk' ? 'text-risk' : 'text-fg-3'}`}
        >
          {subject.meta}
        </span>
      )}
    </button>
  );
}

function Group({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="pt-3">
      <div className="px-[18px] pb-1 font-mono text-[11.5px] text-fg-3">{label}</div>
      {children}
    </div>
  );
}

/** The left column of the Copilot page: what you can ask about (page2 A). */
export function SubjectRail({
  groups,
  selected,
  onSelect,
  onHistory,
  loading,
}: {
  groups: SubjectGroups;
  selected: string | null;
  onSelect: (s: CopilotSubject) => void;
  onHistory: () => void;
  loading: boolean;
}) {
  const icon = (Icon: typeof Layers) => <Icon className="h-4 w-4 flex-none text-fg-3" />;
  return (
    <aside
      aria-label="Ask about"
      className="hidden w-[290px] flex-none flex-col border-r border-line bg-panel md:flex"
    >
      <div className="flex items-center justify-between px-[18px] pb-2 pt-5">
        <h2 className="m-0 text-[17px] font-semibold">Ask about</h2>
        <button type="button" className="btn btn-ghost btn-sm text-fg-2" onClick={onHistory}>
          <History className="h-4 w-4" />
          History
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto pb-4">
        <Row
          subject={ACCOUNT_SUBJECT}
          selected={selected === ACCOUNT_SUBJECT.key}
          onSelect={onSelect}
          icon={icon(PieChart)}
        />
        {groups.sessions.length > 0 && (
          <Group label="Sessions">
            {groups.sessions.map((s) => (
              <Row key={s.key} subject={s} selected={selected === s.key} onSelect={onSelect} />
            ))}
          </Group>
        )}
        {groups.strategies.length > 0 && (
          <Group label="Strategies">
            {groups.strategies.map((s) => (
              <Row
                key={s.key}
                subject={s}
                selected={selected === s.key}
                onSelect={onSelect}
                icon={icon(Layers)}
              />
            ))}
          </Group>
        )}
        {groups.backtests.length > 0 && (
          <Group label="Backtests">
            {groups.backtests.map((s) => (
              <Row
                key={s.key}
                subject={s}
                selected={selected === s.key}
                onSelect={onSelect}
                icon={icon(LineChart)}
              />
            ))}
          </Group>
        )}
        {loading && !groups.sessions.length && !groups.strategies.length && (
          <p className="m-0 flex items-center gap-2 px-[18px] pt-4 text-[12.5px] text-fg-3">
            <CircleDot className="h-3.5 w-3.5 motion-safe:animate-pulse" />
            Loading your sessions and strategies
          </p>
        )}
      </div>
    </aside>
  );
}

/** The phone's version of the rail: a row of chips under the title. */
export function SubjectChips({
  groups,
  selected,
  onSelect,
}: {
  groups: SubjectGroups;
  selected: string | null;
  onSelect: (s: CopilotSubject | null) => void;
}) {
  const all = [ACCOUNT_SUBJECT, ...groups.sessions, ...groups.strategies];
  return (
    <div className="no-scrollbar flex gap-2 overflow-x-auto px-4 pb-1 md:hidden">
      {all.map((s) => {
        const on = selected === s.key;
        return (
          <button
            key={s.key}
            type="button"
            onClick={() => onSelect(on ? null : s)}
            aria-pressed={on}
            className={`inline-flex h-8 flex-none items-center rounded-full border px-3 text-[13px] ${
              on ? 'border-accent/50 bg-accent-soft text-fg' : 'border-line-strong text-fg-2'
            }`}
          >
            {s.kind === 'account' ? 'Account' : s.name}
          </button>
        );
      })}
    </div>
  );
}
