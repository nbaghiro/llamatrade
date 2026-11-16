import { useAgentStore } from '@llamatrade/core/stores/agent';
import { Sparkles } from 'lucide-react';
import { useLocation } from 'react-router-dom';

/** Opens the Copilot side panel on desktop; phones reach Copilot from the tab bar. */
export function AgentFAB() {
  const { pathname } = useLocation();
  const panelOpen = useAgentStore((s) => s.panelOpen);
  const togglePanel = useAgentStore((s) => s.togglePanel);

  const inBuilder = pathname === '/strategies/builder' || pathname.endsWith('/edit');
  if (pathname.startsWith('/copilot') || panelOpen || inBuilder) return null;

  return (
    <button
      type="button"
      onClick={togglePanel}
      aria-label="Ask Copilot"
      title="Ask Copilot"
      className="fixed bottom-6 right-6 z-40 hidden h-12 w-12 place-items-center rounded-full bg-fg text-canvas shadow-lg motion-safe:transition-transform motion-safe:hover:-translate-y-0.5 md:grid"
    >
      <Sparkles className="h-5 w-5" />
    </button>
  );
}
