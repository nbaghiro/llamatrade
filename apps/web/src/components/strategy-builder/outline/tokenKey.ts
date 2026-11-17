import type { OutlineToken } from '../../../lib/outline';

/** Identifies a token across renders: its block and field. */
export const tokenKey = (token: OutlineToken) => `${token.blockId ?? ''}:${token.field}`;
