import { toDate } from '@llamatrade/core/format';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { AlertTriangle, Bell, Info, Settings } from 'lucide-react';
import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';

import { needsAttention, noticeTime } from '../../lib/notifications';
import { Popover } from '../ui/Popover';

const POLL_INTERVAL_MS = 60_000;
const SHOWN_AT_FIRST = 6;

export function NotificationBell() {
  const notifications = useNotificationsStore((s) => s.notifications);
  const unreadCount = useNotificationsStore((s) => s.unreadCount);
  const fetchNotifications = useNotificationsStore((s) => s.fetchNotifications);
  const markAsRead = useNotificationsStore((s) => s.markAsRead);
  const markAllAsRead = useNotificationsStore((s) => s.markAllAsRead);
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
  const shown = showAll ? notifications : notifications.slice(0, SHOWN_AT_FIRST);
  const hidden = notifications.length - shown.length;

  return (
    <Popover
      width={400}
      label="Notifications"
      className="max-sm:fixed max-sm:inset-x-3 max-sm:top-[60px] max-sm:mt-0 max-sm:max-h-[calc(100dvh-72px)] max-sm:!w-auto max-sm:overflow-y-auto"
      trigger={(props) => (
        <button
          type="button"
          {...props}
          aria-label={unreadCount > 0 ? `Notifications, ${unreadCount} unread` : 'Notifications'}
          className={`relative grid h-8 w-8 place-items-center rounded-[8px] transition-colors ${
            props['aria-expanded'] ? 'bg-sunk text-fg' : 'text-fg-2 hover:text-fg'
          }`}
        >
          <Bell className="h-[18px] w-[18px]" />
          {unreadCount > 0 && (
            <b className="absolute right-px top-0.5 h-4 min-w-4 rounded-lg bg-accent px-1 text-center font-mono text-[10px] font-semibold leading-4 text-accent-ink">
              {unreadCount > 99 ? '99+' : unreadCount}
            </b>
          )}
        </button>
      )}
    >
      {(close) => (
        <>
          <div className="flex items-center justify-between gap-2.5 border-b border-line px-4 py-3">
            <b className="font-semibold">Notifications</b>
            {unreadCount > 0 && (
              <button
                type="button"
                onClick={() => {
                  markAllAsRead().catch(() => undefined);
                }}
                className="text-[12.5px] text-fg-3 hover:text-fg"
              >
                Mark all read
              </button>
            )}
          </div>

          <div className="max-h-[min(60vh,480px)] overflow-y-auto">
            {notifications.length === 0 ? (
              <p className="m-0 px-4 py-8 text-center text-[13px] text-fg-3">
                Nothing yet. Fills, finished backtests and anything that needs a look will show
                here.
              </p>
            ) : (
              shown.map((n) => {
                const attention = needsAttention(n);
                const Icon = attention ? AlertTriangle : Info;
                return (
                  <button
                    key={n.id}
                    type="button"
                    onClick={() => {
                      if (!n.isRead) markAsRead(n.id).catch(() => undefined);
                    }}
                    className="grid w-full grid-cols-[22px_minmax(0,1fr)_auto] items-start gap-2.5 border-b border-line px-4 py-[11px] text-left last:border-b-0 hover:bg-sunk"
                  >
                    <Icon className={`mt-0.5 h-4 w-4 ${attention ? 'text-risk' : 'text-fg-3'}`} />
                    <span className="min-w-0">
                      <b className={`block font-semibold ${attention ? 'text-risk' : 'text-fg'}`}>
                        {n.title}
                      </b>
                      <span className="mt-0.5 block text-[12.5px] text-fg-2 line-clamp-2">
                        {n.message}
                      </span>
                    </span>
                    <em className="flex items-center gap-1.5 whitespace-nowrap font-mono text-[11.5px] not-italic text-fg-3">
                      {noticeTime(toDate(n.createdAt), now)}
                      {!n.isRead && (
                        <i
                          aria-label="Unread"
                          className={`h-[7px] w-[7px] rounded-full ${attention ? 'bg-risk' : 'bg-accent'}`}
                        />
                      )}
                    </em>
                  </button>
                );
              })
            )}
            {hidden > 0 && (
              <button
                type="button"
                onClick={() => setShowAll(true)}
                className="w-full border-t border-line px-4 py-2.5 text-[12.5px] text-fg-2 hover:bg-sunk hover:text-fg"
              >
                Show all {notifications.length}
              </button>
            )}
          </div>

          <div className="flex items-center justify-between gap-2.5 border-t border-line px-4 py-3 text-[12.5px]">
            <Link to="/notifications" onClick={close} className="text-accent hover:underline">
              See all notifications
            </Link>
            <Link
              to="/settings/notifications"
              onClick={close}
              className="flex items-center gap-1.5 text-fg-3 hover:text-fg"
            >
              Email settings
              <Settings className="h-4 w-4" />
            </Link>
          </div>
        </>
      )}
    </Popover>
  );
}
