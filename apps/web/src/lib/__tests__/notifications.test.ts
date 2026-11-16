import { NotificationCategory, NotificationSeverity } from '@llamatrade/core/proto/events_pb';
import { NotificationPriority, NotificationType } from '@llamatrade/core/proto/notification_pb';
import { describe, expect, it } from 'vitest';

import { needsAttention, noticeTime } from '../notifications';

const note = (metadata: Record<string, string>, type = NotificationType.INFO) => ({
  type,
  metadata,
});

describe('needsAttention', () => {
  it('flags high and critical priority', () => {
    expect(needsAttention(note({ priority: String(NotificationPriority.HIGH) }))).toBe(true);
    expect(needsAttention(note({ priority: String(NotificationPriority.CRITICAL) }))).toBe(true);
    expect(needsAttention(note({ priority: String(NotificationPriority.MEDIUM) }))).toBe(false);
  });

  it('flags critical severity but not actionable or info', () => {
    expect(needsAttention(note({ severity: String(NotificationSeverity.CRITICAL) }))).toBe(true);
    expect(needsAttention(note({ severity: String(NotificationSeverity.ACTIONABLE) }))).toBe(false);
    expect(needsAttention(note({ severity: String(NotificationSeverity.INFO) }))).toBe(false);
  });

  it('flags frozen, rejected and failed kinds', () => {
    for (const c of [
      NotificationCategory.SLEEVE_FROZEN,
      NotificationCategory.ORDER_REJECTED,
      NotificationCategory.BACKTEST_FAILED,
      NotificationCategory.RISK_BREACH,
    ]) {
      expect(needsAttention(note({ category: String(c) })), String(c)).toBe(true);
    }
  });

  it('leaves routine kinds quiet', () => {
    for (const c of [
      NotificationCategory.BACKTEST_COMPLETED,
      NotificationCategory.ORDER_FILLED,
      NotificationCategory.SESSION_STOPPED,
    ]) {
      expect(needsAttention(note({ category: String(c) })), String(c)).toBe(false);
    }
  });

  it('flags error and alert types', () => {
    expect(needsAttention(note({}, NotificationType.ERROR))).toBe(true);
    expect(needsAttention(note({}, NotificationType.ALERT))).toBe(true);
    expect(needsAttention(note({}, NotificationType.WARNING))).toBe(false);
  });

  it('ignores malformed metadata', () => {
    expect(needsAttention(note({ category: 'frozen', severity: '', priority: '3.5' }))).toBe(false);
  });
});

describe('noticeTime', () => {
  const now = new Date(2026, 10, 13, 12, 0);

  it('shows the time today and the date before', () => {
    expect(noticeTime(new Date(2026, 10, 13, 10, 15), now)).toBe('10:15');
    expect(noticeTime(new Date(2026, 10, 12, 10, 15), now)).toBe('Nov 12');
    expect(noticeTime(null, now)).toBe('');
  });
});
