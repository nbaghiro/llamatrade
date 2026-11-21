import { useAgentStore } from '@llamatrade/core/stores/agent';
import { useStrategiesStore } from '@llamatrade/core/stores/strategies';
import { create } from 'zustand';

import { draftRequest } from './draftQuestions';
import { copilotLimit } from './limits';
import type { SheetStop } from './sheetModel';
import type { CopilotContext, CopilotSubject } from './subjects';

interface CopilotUiState {
  /** What the next question is about; null means the account. */
  context: CopilotContext | null;
  /** The half sheet over the current screen. */
  sheet: SheetStop;
  /** A question Copilot couldn't take, kept until the person tries again. */
  unsent: { text: string; at: Date } | null;
  /** When Copilot was first seen unreachable or limited. */
  downSince: Date | null;
  /** A question `openCopilot` was given, sent once the subject is resolved. */
  pending: string | null;
  setContext: (context: CopilotContext | null) => void;
  setSheet: (stop: SheetStop) => void;
  clearUnsent: () => void;
}

export const useCopilotUi = create<CopilotUiState>()((set) => ({
  context: null,
  sheet: 'closed',
  unsent: null,
  downSince: null,
  pending: null,
  setContext: (context) => set({ context }),
  setSheet: (sheet) => set({ sheet }),
  clearUnsent: () => set({ unsent: null }),
}));

/** The agent service limits messages per minute; the notice clears after that window. */
const RATE_WINDOW_MS = 60_000;

/** The strategy name and code Copilot is given for a subject; context ids themselves aren't sent yet. */
function strategyContext(subject: CopilotSubject | null): { name?: string; dsl?: string } {
  if (!subject?.strategyId) return {};
  const { strategies, details } = useStrategiesStore.getState();
  const strategy = details[subject.strategyId] ?? strategies.find((s) => s.id === subject.strategyId);
  return { name: strategy?.name ?? subject.name, dsl: strategy?.dslCode || undefined };
}

/**
 * Sends a message with the subject's strategy as context. When Copilot can't take it, the
 * question is kept as unsent instead of lost (limits B).
 */
export async function sendToCopilot(text: string, subject: CopilotSubject | null, page: string): Promise<void> {
  const t = text.trim();
  if (!t) return;
  const agent = useAgentStore.getState();
  if (agent.isStreaming) return;
  const ctx = strategyContext(subject);
  useCopilotUi.setState({ unsent: null });
  useAgentStore.setState({ error: null });
  await agent.sendMessage(t, ctx.dsl, ctx.name, page);
  const after = useAgentStore.getState();
  const limit = copilotLimit(after);
  if (limit === 'rate') {
    const err = after.error;
    setTimeout(() => {
      if (useAgentStore.getState().error === err) useAgentStore.setState({ error: null });
    }, RATE_WINDOW_MS);
  }
  if (limit) {
    const msgs = after.messages;
    const last = msgs[msgs.length - 1];
    if (last && last.id.startsWith('temp-') && last.content === t) {
      useAgentStore.setState({ messages: msgs.slice(0, -1) });
    }
    useCopilotUi.setState((s) => ({ unsent: { text: t, at: new Date() }, downSince: s.downSince ?? new Date() }));
  } else {
    useCopilotUi.setState({ downSince: null });
  }
}

export interface OpenOptions {
  /** A question to start a new conversation with. */
  question?: string;
  /** Opens the half sheet over the current screen (default); false leaves navigation to the caller. */
  sheet?: boolean;
}

/**
 * Opens Copilot about a subject from any screen. With a question it starts a new conversation and
 * asks it at once; the half sheet shows the answer over the screen the person is on.
 */
export function openCopilot(context: CopilotContext, options: OpenOptions = {}): void {
  const { sheet = true, question } = options;
  const ui = useCopilotUi.getState();
  const changed = ui.context?.kind !== context.kind || ui.context?.id !== context.id;
  ui.setContext(context);
  if (question || changed) useAgentStore.getState().startNewChat();
  if (sheet) ui.setSheet('half');
  if (question) useCopilotUi.setState({ pending: question });
}

/** Takes the pending question once. */
export function takePendingQuestion(): string | null {
  const q = useCopilotUi.getState().pending;
  if (q) useCopilotUi.setState({ pending: null });
  return q;
}

/** A strategy description goes out as a draft request, so Copilot asks its questions first (draft2 B). */
export async function startDraft(description: string, subject: CopilotSubject | null): Promise<void> {
  if (useAgentStore.getState().messages.length) useAgentStore.getState().startNewChat();
  await sendToCopilot(draftRequest(description), subject, 'copilot');
}
