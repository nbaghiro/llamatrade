/**
 * Shared "or continue with" OAuth buttons for the auth pages. Brand marks keep their
 * real colours (not themed). Presentational for now — wire `onGoogle`/`onMicrosoft`
 * to real OAuth start endpoints when the backend supports it.
 */

function GoogleMark() {
  return (
    <svg width="16" height="16" viewBox="0 0 18 18" aria-hidden="true" className="flex-none">
      <path
        fill="#4285F4"
        d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.92c1.71-1.57 2.68-3.88 2.68-6.62Z"
      />
      <path
        fill="#34A853"
        d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.92-2.26c-.8.54-1.84.86-3.04.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z"
      />
      <path
        fill="#FBBC05"
        d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33Z"
      />
      <path
        fill="#EA4335"
        d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.9 11.43 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z"
      />
    </svg>
  );
}

function MicrosoftMark() {
  return (
    <svg width="15" height="15" viewBox="0 0 20 20" aria-hidden="true" className="flex-none">
      <rect x="1" y="1" width="8" height="8" fill="#F25022" />
      <rect x="11" y="1" width="8" height="8" fill="#7FBA00" />
      <rect x="1" y="11" width="8" height="8" fill="#00A4EF" />
      <rect x="11" y="11" width="8" height="8" fill="#FFB900" />
    </svg>
  );
}

interface SocialAuthButtonsProps {
  /** Optional real handlers; default no-op keeps the buttons presentational. */
  onGoogle?: () => void;
  onMicrosoft?: () => void;
  disabled?: boolean;
}

export function SocialAuthButtons({ onGoogle, onMicrosoft, disabled }: SocialAuthButtonsProps) {
  return (
    <div className="mt-5">
      <div className="flex items-center gap-3" aria-hidden="true">
        <span className="h-px flex-1 bg-ink/15" />
        <span className="font-mono text-[10px] font-bold uppercase tracking-[0.2em] text-ink/40">
          or
        </span>
        <span className="h-px flex-1 bg-ink/15" />
      </div>

      <div className="mt-5 space-y-3">
        <button
          type="button"
          className="btn btn-secondary btn-lg w-full"
          onClick={onGoogle}
          disabled={disabled}
        >
          <GoogleMark />
          Continue with Google
        </button>
        <button
          type="button"
          className="btn btn-secondary btn-lg w-full"
          onClick={onMicrosoft}
          disabled={disabled}
        >
          <MicrosoftMark />
          Continue with Microsoft
        </button>
      </div>
    </div>
  );
}
