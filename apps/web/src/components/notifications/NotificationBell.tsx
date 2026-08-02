import { NotificationSeverity } from '@llamatrade/core/proto/events_pb';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { Bell, CheckCheck } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { NavLink } from 'react-router-dom';

import { severityBadge } from '../../types/notifications';
import { Badge } from '../common/Badge';

const POLL_INTERVAL_MS = 60_000;

function timeAgo(seconds: bigint | undefined): string {
  if (!seconds) return '';
  const delta = Math.max(0, Date.now() / 1000 - Number(seconds));
  if (delta < 60) return 'just now';
  if (delta < 3600) return `${Math.floor(delta / 60)}m ago`;
  if (delta < 86400) return `${Math.floor(delta / 3600)}h ago`;
  return `${Math.floor(delta / 86400)}d ago`;
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const { notifications, unreadCount, fetchNotifications, markAsRead, markAllAsRead } =
    useNotificationsStore();
  const timer = useRef<ReturnType<typeof setInterval> | null>(null);

  useEffect(() => {
    void fetchNotifications();
    timer.current = setInterval(() => void fetchNotifications(), POLL_INTERVAL_MS);
    return () => {
      if (timer.current) clearInterval(timer.current);
    };
  }, [fetchNotifications]);

  return (
    <div className="relative">
      <button
        onClick={() => setOpen(!open)}
        title="Notifications"
        aria-label="Notifications"
        className={`relative grid h-9 w-9 place-items-center border-2 transition-colors ${
          open
            ? 'border-ink bg-ink/5 text-ink'
            : 'border-transparent text-ink/60 hover:bg-ink/5 hover:text-ink'
        }`}
      >
        <Bell className="h-[18px] w-[18px]" />
        {unreadCount > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[18px] h-[18px] px-1 grid place-items-center bg-orange-500 border-2 border-ink text-[10px] font-mono font-bold text-ink">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </button>

      {open && (
        <>
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />
          <div className="dropdown right-0 top-full mt-2 w-96 max-h-[70vh] overflow-y-auto">
            <div className="flex items-center justify-between px-4 py-3 border-b-2 border-ink">
              <p className="text-sm font-medium text-ink">Notifications</p>
              {unreadCount > 0 && (
                <button
                  onClick={() => void markAllAsRead()}
                  className="flex items-center gap-1 text-[11px] font-mono uppercase tracking-wide text-ink/60 hover:text-ink"
                >
                  <CheckCheck className="w-3.5 h-3.5" />
                  Mark all read
                </button>
              )}
            </div>

            {notifications.length === 0 ? (
              <p className="px-4 py-6 text-sm text-ink/60">Nothing yet.</p>
            ) : (
              notifications.map((n) => {
                const severity = Number(n.metadata['severity'] ?? 0) as NotificationSeverity;
                return (
                  <button
                    key={n.id}
                    onClick={() => {
                      if (!n.isRead) void markAsRead(n.id);
                    }}
                    className={`w-full text-left px-4 py-3 border-b border-ink/10 hover:bg-ink/5 transition-colors ${
                      n.isRead ? 'opacity-60' : ''
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {!n.isRead && <span className="h-2 w-2 bg-orange-500 shrink-0" />}
                      <p className="text-sm font-medium text-ink truncate">{n.title}</p>
                      <Badge variant={severityBadge(severity)} className="ml-auto shrink-0">
                        {timeAgo(n.createdAt?.seconds)}
                      </Badge>
                    </div>
                    <p className="mt-1 text-[13px] text-ink/70 line-clamp-2">{n.message}</p>
                  </button>
                );
              })
            )}

            <NavLink
              to="/settings?tab=notifications"
              onClick={() => setOpen(false)}
              className="block px-4 py-2.5 text-[11px] font-mono uppercase tracking-wide text-ink/60 hover:text-ink hover:bg-ink/5"
            >
              Notification settings
            </NavLink>
          </div>
        </>
      )}
    </div>
  );
}
