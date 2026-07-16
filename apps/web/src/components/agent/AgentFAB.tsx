/** Floating action button that toggles the overlay side-panel Copilot ("quick ask"). */

import { useLocation } from 'react-router-dom';

import { useAgentStore } from '../../store/agent';

/**
 * Custom AI/Magic icon with sparkles
 */
function MagicIcon({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 24 24" fill="none" className={className} xmlns="http://www.w3.org/2000/svg">
      {/* Main sparkle */}
      <path
        d="M12 2L13.5 8.5L20 10L13.5 11.5L12 18L10.5 11.5L4 10L10.5 8.5L12 2Z"
        fill="currentColor"
        stroke="currentColor"
        strokeWidth="1"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      {/* Small sparkle top-right */}
      <path d="M19 2L19.75 4.25L22 5L19.75 5.75L19 8L18.25 5.75L16 5L18.25 4.25L19 2Z" fill="currentColor" opacity="0.8" />
      {/* Small sparkle bottom-left */}
      <path d="M5 16L5.75 18.25L8 19L5.75 19.75L5 22L4.25 19.75L2 19L4.25 18.25L5 16Z" fill="currentColor" opacity="0.8" />
    </svg>
  );
}

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
