/**
 * Agent Floating Action Button.
 *
 * A floating button that opens the agent chat as a centered dialog.
 * Can be placed in the Layout component for global access.
 */

import { X } from 'lucide-react';

import { useAgentStore } from '../../store/agent';

import { AgentChat } from './AgentChat';

interface AgentFABProps {
  /** Current page for context-aware prompts */
  page?: string;
  /** Current strategy DSL code (auto-included in context) */
  strategyDSL?: string;
  /** Current strategy name */
  strategyName?: string;
}

/**
 * Custom AI/Magic icon with sparkles
 */
function MagicIcon({ className }: { className?: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      className={className}
      xmlns="http://www.w3.org/2000/svg"
    >
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
      <path
        d="M19 2L19.75 4.25L22 5L19.75 5.75L19 8L18.25 5.75L16 5L18.25 4.25L19 2Z"
        fill="currentColor"
        opacity="0.8"
      />
      {/* Small sparkle bottom-left */}
      <path
        d="M5 16L5.75 18.25L8 19L5.75 19.75L5 22L4.25 19.75L2 19L4.25 18.25L5 16Z"
        fill="currentColor"
        opacity="0.8"
      />
    </svg>
  );
}

export function AgentFAB({ page, strategyDSL, strategyName }: AgentFABProps) {
  const { isOpen, toggleChat, closeChat } = useAgentStore();

  return (
    <>
      {/* FAB button */}
      <button
        onClick={toggleChat}
        className={`fixed bottom-6 right-6 z-40 w-14 h-14 rounded-full shadow-lg transition-all duration-200 flex items-center justify-center ${
          isOpen
            ? 'bg-gray-600 hover:bg-gray-700'
            : 'hover:scale-105 hover:shadow-xl'
        }`}
        style={
          !isOpen
            ? {
                background: 'linear-gradient(135deg, #2563EB 0%, #0891B2 50%, #059669 100%)',
              }
            : undefined
        }
        title={isOpen ? 'Close Copilot' : 'Open Copilot'}
      >
        {isOpen ? (
          <X className="w-6 h-6 text-white" />
        ) : (
          <MagicIcon className="w-6 h-6 text-white" />
        )}
      </button>

      {/* Chat dialog (centered modal) */}
      {isOpen && (
        <>
          {/* Backdrop */}
          <div
            className="fixed inset-0 bg-black/30 z-40"
            onClick={closeChat}
          />

          {/* Dialog */}
          <AgentChat
            page={page}
            strategyDSL={strategyDSL}
            strategyName={strategyName}
            onClose={closeChat}
          />
        </>
      )}
    </>
  );
}
