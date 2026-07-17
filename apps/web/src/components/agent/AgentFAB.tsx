/** Floating action button that toggles the overlay side-panel Copilot ("quick ask"). */

import { useAgentStore } from '@llamatrade/core/stores/agent';
import { useLocation } from 'react-router-dom';

import { MagicIcon } from '../common/MagicIcon';

export function AgentFAB() {
  const location = useLocation();
  const panelOpen = useAgentStore((s) => s.panelOpen);
  const togglePanel = useAgentStore((s) => s.togglePanel);

  // Redundant on the full-page Copilot, and while the overlay panel is open.
  if (location.pathname === '/copilot' || panelOpen) return null;

  return (
    <button
      type="button"
      onClick={togglePanel}
      className="fixed bottom-6 right-6 z-40 flex h-12 w-12 items-center justify-center border-2 border-orange-500 bg-ink shadow transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lg"
      title="Open Copilot"
    >
      <MagicIcon className="h-5 w-5 text-orange-500" />
    </button>
  );
}
