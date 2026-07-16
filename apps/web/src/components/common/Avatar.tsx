import { useState } from 'react';

interface AvatarProps {
  /** Profile photo URL from the account; falls back to initials when empty. */
  avatarUrl?: string;
  firstName?: string;
  lastName?: string;
  email?: string;
  /** Square size in px. Defaults to 32. */
  size?: number;
  className?: string;
}

/** Up-to-two-letter initials from name, else the email local-part, else "?". */
function initialsFrom(firstName?: string, lastName?: string, email?: string): string {
  const first = firstName?.trim();
  const last = lastName?.trim();
  if (first || last) {
    return `${first?.[0] ?? ''}${last?.[0] ?? ''}`.toUpperCase();
  }
  const local = email?.split('@')[0]?.replace(/[^a-zA-Z]/g, '');
  if (local) return local.slice(0, 2).toUpperCase();
  return '?';
}

/**
 * Account avatar: renders the profile photo when the account carries one,
 * otherwise a Monolith initials tile (ink ground, bone text). Falls back to
 * initials if the image URL fails to load.
 */
export function Avatar({ avatarUrl, firstName, lastName, email, size = 32, className = '' }: AvatarProps) {
  const [errored, setErrored] = useState(false);
  const dims = { width: size, height: size };
  const name = [firstName, lastName].filter(Boolean).join(' ');

  if (avatarUrl && !errored) {
    return (
      <img
        src={avatarUrl}
        alt={name || 'Profile'}
        style={dims}
        className={`flex-none border-2 border-ink object-cover ${className}`}
        onError={() => setErrored(true)}
      />
    );
  }

  return (
    <span
      style={dims}
      className={`flex-none grid place-items-center border-2 border-ink bg-ink text-bone font-mono font-bold uppercase leading-none ${className}`}
      aria-label={name ? `${name} avatar` : 'Profile avatar'}
      role="img"
    >
      <span style={{ fontSize: Math.round(size * 0.4) }}>{initialsFrom(firstName, lastName, email)}</span>
    </span>
  );
}
