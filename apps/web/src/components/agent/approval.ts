export interface ApprovalArg {
  label: string;
  value: string;
}

export interface ArgChange {
  label: string;
  value: string;
}

/** The fields the person changed, in the card's order, ignoring surrounding spaces. */
export function changedArgs(
  original: readonly ApprovalArg[],
  edited: readonly string[]
): ArgChange[] {
  return original
    .map((a, i) => ({ label: a.label, value: (edited[i] ?? a.value).trim() }))
    .filter((c, i) => c.value !== '' && c.value !== original[i].value.trim());
}

/** The message that asks Copilot to propose the run again with the changed values. */
export function changeMessage(changes: readonly ArgChange[]): string {
  if (!changes.length) return '';
  const parts = changes.map((c) => `${c.label} ${c.value}`);
  const joined =
    parts.length === 1
      ? parts[0]
      : `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
  return `Run it again with ${joined} instead.`;
}

/** The one line an answered proposal leaves in the thread. */
export function approvalRecord(
  title: string,
  decision: 'approved' | 'declined' | 'change',
  args: readonly ApprovalArg[]
): string {
  const verb =
    decision === 'approved'
      ? 'You approved'
      : decision === 'declined'
        ? 'You declined'
        : 'You changed';
  const detail = args
    .filter((a) => a.label !== 'Strategy')
    .map((a) => a.value)
    .join(' · ');
  return `${verb}: ${title.charAt(0).toLowerCase()}${title.slice(1)}${detail ? ` · ${detail}` : ''}`;
}
