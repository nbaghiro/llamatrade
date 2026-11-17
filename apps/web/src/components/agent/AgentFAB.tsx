import { useAgentStore } from '@llamatrade/core/stores/agent';
import { Sparkles } from 'lucide-react';
import { useEffect } from 'react';
import { useLocation } from 'react-router-dom';

/**
 * Opens the Copilot side panel; on phones it rises as a half sheet over the current screen.
 * ⌘J (Ctrl+J) toggles it from anywhere in the app.
 */
export function AgentFAB() {
  const { pathname } = useLocation();
  const panelOpen = useAgentStore((s) => s.panelOpen);
  const togglePanel = useAgentStore((s) => s.togglePanel);
  const onCopilot = pathname.startsWith('/copilot');

  useEffect(() => {
    if (onCopilot) return;
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && !e.shiftKey && !e.altKey && e.key.toLowerCase() === 'j') {
        e.preventDefault();
        togglePanel();
      }
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onCopilot, togglePanel]);

  const inBuilder = pathname === '/strategies/builder' || pathname.endsWith('/edit');
  if (onCopilot || panelOpen || inBuilder) return null;

  return (
    <button
      type="button"
      onClick={togglePanel}
      aria-label="Ask Copilot"
      title="Ask Copilot (⌘J)"
      className="fixed bottom-[100px] right-4 z-40 grid h-12 w-12 place-items-center rounded-full bg-fg text-canvas shadow-lg motion-safe:transition-transform motion-safe:hover:-translate-y-0.5 md:bottom-6 md:right-6"
    >
      <Sparkles className="h-5 w-5" />
    </button>
  );
}
