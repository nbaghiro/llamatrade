import type { AlpacaCredentialsListItem } from '@llamatrade/core/proto/auth_pb';

export type Kind = 'paper' | 'live';

/** The active stored key of one kind, or null. */
export function activeOf(
  credentials: readonly AlpacaCredentialsListItem[],
  kind: Kind
): AlpacaCredentialsListItem | null {
  return credentials.find((c) => c.isPaper === (kind === 'paper') && c.isActive) ?? null;
}
