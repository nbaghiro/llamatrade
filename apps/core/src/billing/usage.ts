/** Usage-period and meter maths shared by the web and mobile plan screens. */

export interface UsagePeriod {
  start: Date;
  /** Last day of the period, at midnight local time. */
  end: Date;
}

/** The calendar month containing `now`, in local time. */
export function usagePeriod(now: Date): UsagePeriod {
  return {
    start: new Date(now.getFullYear(), now.getMonth(), 1),
    end: new Date(now.getFullYear(), now.getMonth() + 1, 0),
  };
}

export interface MeterState {
  /** Bar fill, 0 to 1. */
  fraction: number;
  unlimited: boolean;
  atLimit: boolean;
  /** "4 remaining", "Unlimited" or "At the limit". */
  note: string;
}

/** A used/limit pair as a meter. A negative limit means unlimited; zero means not included. */
export function meterState(used: number, limit: number): MeterState {
  const safeUsed = Math.max(0, used);
  if (limit < 0) {
    return { fraction: 0, unlimited: true, atLimit: false, note: "Unlimited" };
  }
  if (limit === 0) {
    return {
      fraction: 0,
      unlimited: false,
      atLimit: safeUsed > 0,
      note: "Not included",
    };
  }
  const atLimit = safeUsed >= limit;
  return {
    fraction: Math.min(1, safeUsed / limit),
    unlimited: false,
    atLimit,
    note: atLimit
      ? "At the limit"
      : `${(limit - safeUsed).toLocaleString("en-US")} remaining`,
  };
}
