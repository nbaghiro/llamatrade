/** LlamaTrade AI/Copilot sparkle mark — shared by the floating Copilot button and the strategy Copilot bar. */
export function MagicIcon({ className }: { className?: string }) {
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
