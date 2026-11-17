import { toDate } from '@llamatrade/core/format';
import { NotificationCategory } from '@llamatrade/core/proto/events_pb';
import { SleeveStatus } from '@llamatrade/core/proto/ledger_pb';
import type { Notification } from '@llamatrade/core/proto/notification_pb';
import { useDashboardStore } from '@llamatrade/core/stores/dashboard';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { useTradingStore } from '@llamatrade/core/stores/trading';
import { AlertTriangle, Bell, Check, Info, LineChart, type LucideIcon } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';

import { etClock, etParts } from '../../lib/marketClock';
import { needsAttention, noticeTime } from '../../lib/notifications';
import { LaneMarker } from '../charts/LaneMarker';
import { useAttentionEntries } from '../home/useAttentionEntries';
import { useSessionRows } from '../shell/useSessionRows';
import { Popover } from '../ui/Popover';

import {
  CLOSE_MIN,
  dayFraction,
  minuteLabel,
  OPEN_MIN,
  todayLanes,
  type TodayLane,
} from './todayLanes';

const POLL_INTERVAL_MS = 60_000;
const SHOWN_AT_FIRST = 5;

const longDay = (d: Date) =>
  d.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    timeZone: 'America/New_York',
  });

const pct = (f: number) => `${(f * 100).toFixed(2)}%`;

function categoryOf(n: Notification): NotificationCategory | null {
  const raw = Number(n.metadata.category);
  return Number.isInteger(raw) ? (raw as NotificationCategory) : null;
}

function noticeIcon(n: Notification): LucideIcon {
  const c = categoryOf(n);
  if (c === NotificationCategory.ORDER_FILLED) return Check;
  if (c === NotificationCategory.BACKTEST_COMPLETED) return LineChart;
  return Info;
}

/** Today's sessions from the open to the close, each fill where it happened (notifications2 A). */
export function TodayLanes({ lanes, now }: { lanes: readonly TodayLane[]; now: Date }) {
  const nowMin = etParts(now).minutes;
  const open = nowMin >= OPEN_MIN && nowMin <= CLOSE_MIN;
  const nowLeft = pct(dayFraction(nowMin));
  return (
    <div className="px-4 pb-3 pt-2">
      <div className="relative grid grid-cols-[128px_minmax(0,1fr)] gap-x-3">
        {lanes.map((l) => (
          <div key={l.id} className="contents">
            <span
              className={`truncate py-[5px] text-[12px] ${l.frozen ? 'font-medium text-risk' : 'text-fg-2'}`}
            >
              {l.name}
            </span>
            <span className="relative h-6">
              <i
                aria-hidden="true"
                className={`absolute inset-x-0 top-1/2 border-t ${l.frozen ? 'border-t-[1.5px] border-risk' : 'border-dashed border-line-strong'}`}
              />
              {l.fills.map((f) => (
                <LaneMarker
                  key={f.minute}
                  shape="dot"
                  tone={l.frozen ? 'risk' : 'accent'}
                  count={f.count > 1 ? f.count : undefined}
                  positioned
                  title={`${f.count} fill${f.count === 1 ? '' : 's'} from ${minuteLabel(f.minute)} ET`}
                  style={{ left: pct(dayFraction(f.minute)) }}
                />
              ))}
            </span>
          </div>
        ))}
        <span />
        <span className="relative mt-1 h-4 font-mono text-[10.5px] text-fg-3">
          <span className="absolute left-0">9:30</span>
          <span className="absolute -translate-x-1/2" style={{ left: pct(dayFraction(13 * 60)) }}>
            13:00
          </span>
          <span className="absolute right-0">16:00</span>
          {open && (
            <b
              className="absolute -translate-x-1/2 bg-panel px-1 font-semibold text-fg"
              style={{ left: nowLeft }}
            >
              {etClock(now)}
            </b>
          )}
        </span>
        {open && (
          <i
            aria-hidden="true"
            className="pointer-events-none absolute bottom-4 top-0 border-l-[1.5px] border-fg"
            style={{ left: `calc(140px + (100% - 140px) * ${dayFraction(nowMin).toFixed(4)})` }}
          />
        )}
      </div>
    </div>
  );
}

/** The bell opens on today drawn as lanes, then what needs you, then the rest (notifications2 A). */
export function NotificationBell() {
  const notifications = useNotificationsStore((s) => s.notifications);
  const unreadCount = useNotificationsStore((s) => s.unreadCount);
  const fetchNotifications = useNotificationsStore((s) => s.fetchNotifications);
  const markAsRead = useNotificationsStore((s) => s.markAsRead);
  const markAllAsRead = useNotificationsStore((s) => s.markAllAsRead);
  const sessionRows = useSessionRows();
  const orders = useTradingStore((s) => s.orders);
  const sleeves = useTradingStore((s) => s.sleeves);
  const dashboardFrozen = useDashboardStore((s) => s.frozenSleeves);
  const attention = useAttentionEntries();
  const [showAll, setShowAll] = useState(false);

  useEffect(() => {
    const load = () => {
      fetchNotifications().catch(() => undefined);
    };
    load();
    const timer = setInterval(load, POLL_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [fetchNotifications]);

  const now = new Date();
  const lanes = useMemo(() => {
    const frozen = new Set<string>([
      ...(dashboardFrozen ?? []).map((f) => f.id),
      ...sleeves.filter((s) => s.status === SleeveStatus.FROZEN).map((s) => s.id),
    ]);
    return todayLanes(
      sessionRows.map((r) => ({
        id: r.session.id,
        name: r.name,
        isActive: r.session.isActive,
        sleeveId: r.session.sleeveId,
      })),
      orders.map((o) => ({
        sessionId: o.sessionId,
        status: o.status,
        filledAt: toDate(o.filledAt),
      })),
      frozen,
      new Date()
    );
  }, [sessionRows, orders, sleeves, dashboardFrozen]);

  const raised = new Set(attention.map((a) => a.id));
  const earlier = notifications.filter((n) => !raised.has(`notice-${n.id}`));
  const shown = showAll ? earlier : earlier.slice(0, SHOWN_AT_FIRST);
  const hidden = earlier.length - shown.length;
  const todayCount = notifications.filter((n) => {
    const at = toDate(n.createdAt);
    return at !== null && at.toDateString() === now.toDateString();
  }).length;
  const urgent = attention.length > 0;

  return (
    <Popover
      width={460}
      label="Notifications"
      className="max-sm:fixed max-sm:inset-x-3 max-sm:top-[60px] max-sm:mt-0 max-sm:max-h-[calc(100dvh-72px)] max-sm:!w-auto max-sm:overflow-y-auto"
      trigger={(props) => (
        <button
          type="button"
          {...props}
          aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'}
          className={`relative grid h-[34px] w-[34px] place-items-center rounded-full transition-colors ${
            props['aria-expanded']
              ? 'bg-sunk text-fg shadow-[inset_0_0_0_1px_rgb(var(--line-strong))]'
              : 'text-fg-2 hover:text-fg'
          }`}
        >
          <Bell className="h-[18px] w-[18px]" />
          {(unreadCount > 0 || urgent) && (
            <i
              aria-hidden="true"
              className={`absolute right-[7px] top-1.5 h-[7px] w-[7px] rounded-full shadow-[0_0_0_2px_rgb(var(--canvas))] ${urgent ? 'bg-risk' : 'bg-accent'}`}
            />
          )}
        </button>
      )}
    >
      {(close) => (
        <>
          <div className="flex items-center gap-2.5 border-b border-line px-4 py-3">
            <b className="font-semibold">Today</b>
            <span className="text-[12px] text-fg-3">{longDay(now)}</span>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => {
                  markAllAsRead().catch(() => undefined);
                }}
                className="ml-auto text-[12.5px] text-accent hover:underline"
              >
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-[min(70vh,560px)] overflow-y-auto">
            {lanes.length > 0 && (
              <div className="border-b border-line">
                <TodayLanes lanes={lanes} now={now} />
              </div>
            )}

            {attention.length > 0 && (
              <section className="border-b border-line">
                <div className="kicker px-4 pb-1 pt-3 uppercase tracking-[0.06em]">Needs you</div>
                {attention.map((a) => (
                  <div
                    key={a.id}
                    className="grid grid-cols-[22px_minmax(0,1fr)] items-start gap-2.5 px-4 py-2.5"
                  >
                    <AlertTriangle className="mt-0.5 h-4 w-4 text-risk" />
                    <span className="min-w-0">
                      <b className="block font-semibold text-fg">{a.title}</b>
                      {a.detail && (
                        <span className="mt-0.5 block text-[12.5px] text-fg-2">{a.detail}</span>
                      )}
                      <Link
                        to={a.href}
                        onClick={close}
                        className="mt-2 inline-flex h-7 items-center rounded-[7px] border border-risk-line bg-risk-soft px-2.5 text-[12.5px] font-medium text-fg hover:border-risk"
                      >
                        Review
                      </Link>
                    </span>
                  </div>
                ))}
              </section>
            )}

            {earlier.length === 0 && attention.length === 0 ? (
              <p className="m-0 px-4 py-8 text-center text-[13px] text-fg-3">
                Nothing yet. Fills, finished backtests and anything that needs a look will show
                here.
              </p>
            ) : (
              earlier.length > 0 && (
                <section>
                  <div className="kicker px-4 pb-1 pt-3 uppercase tracking-[0.06em]">Earlier</div>
                  {shown.map((n) => {
                    const amber = needsAttention(n);
                    const Icon = amber ? AlertTriangle : noticeIcon(n);
                    return (
                      <button
                        key={n.id}
                        type="button"
                        onClick={() => {
                          if (!n.isRead) markAsRead(n.id).catch(() => undefined);
                        }}
                        className="grid w-full grid-cols-[26px_minmax(0,1fr)_auto] items-start gap-2.5 border-b border-line px-4 py-[11px] text-left last:border-b-0 hover:bg-sunk"
                      >
                        <span
                          className={`grid h-[26px] w-[26px] place-items-center rounded-full ${amber ? 'bg-risk-soft text-risk' : 'bg-sunk text-fg-3'}`}
                        >
                          <Icon className="h-3.5 w-3.5" />
                        </span>
                        <span className="min-w-0">
                          <span className="block text-[13px] text-fg">{n.title}</span>
                          <span className="mt-0.5 block text-[12.5px] text-fg-2 line-clamp-2">
                            {n.message}
                          </span>
                        </span>
                        <em className="flex items-center gap-1.5 whitespace-nowrap font-mono text-[11.5px] not-italic text-fg-3">
                          {noticeTime(toDate(n.createdAt), now)}
                          {!n.isRead && (
                            <i
                              aria-label="Unread"
                              className="h-[7px] w-[7px] rounded-full bg-accent"
                            />
                          )}
                        </em>
                      </button>
                    );
                  })}
                  {hidden > 0 && (
                    <button
                      type="button"
                      onClick={() => setShowAll(true)}
                      className="w-full border-t border-line px-4 py-2.5 text-[12.5px] text-fg-2 hover:bg-sunk hover:text-fg"
                    >
                      Show {hidden} more
                    </button>
                  )}
                </section>
              )
            )}
          </div>

          <div className="flex items-center justify-between gap-2.5 border-t border-line bg-sunk px-4 py-2.5 text-[12.5px]">
            <span className="text-fg-3">{todayCount} today</span>
            <Link to="/notifications" onClick={close} className="text-accent hover:underline">
              All activity
            </Link>
          </div>
        </>
      )}
    </Popover>
  );
}
