/**
 * How the preference grid resolves, the same way the notification service routes. Category and
 * channel values are the proto enum numbers; `notifications.ts` supplies the real tables.
 */

export interface Routing {
  email: number;
  webhook: number;
  /** External channels each category can reach; preferences can only narrow these. */
  reach: ReadonlyMap<number, readonly number[]>;
  /** Categories that always email, whatever the grid says. */
  alwaysEmail: ReadonlySet<number>;
}

export interface ChannelPrefLike {
  channel: number;
  enabled: boolean;
  categories: readonly number[];
}

/** locked: always emails; unavailable: the category never goes to this channel. */
export type CellState = 'locked' | 'on' | 'off' | 'unavailable';

export function canReach(r: Routing, channel: number, category: number): boolean {
  return (r.reach.get(category) ?? []).includes(channel);
}

function chosen(prefs: readonly ChannelPrefLike[], channel: number, category: number): boolean {
  const pref = prefs.find((p) => p.channel === channel);
  if (!pref) return true;
  if (!pref.enabled) return false;
  return pref.categories.length === 0 || pref.categories.includes(category);
}

export function cellState(r: Routing, prefs: readonly ChannelPrefLike[], channel: number, category: number): CellState {
  if (channel === r.email && r.alwaysEmail.has(category)) return 'locked';
  if (!canReach(r, channel, category)) return 'unavailable';
  return chosen(prefs, channel, category) ? 'on' : 'off';
}

/**
 * The preferences to save after flipping one box. An empty category list means every default, so
 * a channel with everything on saves as empty and one with nothing on saves as disabled.
 */
export function toggledPreferences(
  r: Routing,
  prefs: readonly ChannelPrefLike[],
  channel: number,
  category: number,
): ChannelPrefLike[] {
  return [r.email, r.webhook].map((ch) => {
    const existing = prefs.find((p) => p.channel === ch);
    const keep = existing ?? { channel: ch, enabled: true, categories: [] };
    if (ch !== channel) return keep;
    const eligible = [...r.reach.keys()].filter((c) => canReach(r, ch, c)).sort((a, b) => a - b);
    if (!eligible.includes(category)) return keep;
    const on = new Set(eligible.filter((c) => chosen(prefs, ch, c)));
    if (on.has(category)) on.delete(category);
    else on.add(category);
    if (on.size === 0) return { channel: ch, enabled: false, categories: [] };
    if (on.size === eligible.length) return { channel: ch, enabled: true, categories: [] };
    return { channel: ch, enabled: true, categories: eligible.filter((c) => on.has(c)) };
  });
}

/** "Email on", "Email off" or "Email for 4 of 12", for the Account list. */
export function emailSummary(r: Routing, prefs: readonly ChannelPrefLike[]): string {
  const eligible = [...r.reach.keys()].filter((c) => canReach(r, r.email, c) && !r.alwaysEmail.has(c));
  const on = eligible.filter((c) => chosen(prefs, r.email, c)).length;
  if (on === eligible.length) return 'Email on';
  if (on === 0) return 'Email off';
  return `Email for ${on} of ${eligible.length}`;
}
