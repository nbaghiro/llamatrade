import { toDate } from '@llamatrade/core/format';
import type { Notification } from '@llamatrade/core/proto/notification_pb';
import { useNotificationsStore } from '@llamatrade/core/stores/notifications';
import { AlertTriangle, Bell, ChevronLeft } from 'lucide-react';
import { useEffect } from 'react';
import { Link } from 'react-router-dom';

import { EmptyState, PanelError, Segmented, SkeletonRows } from '../../components/ui';
import { asSentence } from '../../lib/format';
import { needsAttention, noticeTime } from '../../lib/notifications';
import { metadataCategoryLabel } from '../../types/notifications';

import { groupByDay } from './groupByDay';

type Filter = 'all' | 'unread';

function NoticeRow({ n, now, onRead }: { n: Notification; now: Date; onRead: () => void }) {
  const attention = needsAttention(n);
  const category = metadataCategoryLabel(n.metadata.category);
  return (
    <button
      type="button"
      onClick={onRead}
      aria-label={n.isRead ? undefined : `${n.title}, unread`}
      className="flex w-full gap-2.5 border-b border-line px-3.5 py-[11px] text-left text-[12.5px] last:border-b-0 hover:bg-sunk md:px-4"
    >
      <i
        aria-hidden="true"
        className={`mt-1.5 h-[7px] w-[7px] flex-none rounded-full ${
          n.isRead ? 'bg-transparent' : attention ? 'bg-risk' : 'bg-accent'
        }`}
      />
      <span className="min-w-0 flex-1">
        <b
          className={`flex items-center gap-1.5 ${n.isRead ? 'font-medium' : 'font-semibold'} ${
            attention ? 'text-risk' : 'text-fg'
          }`}
        >
          {attention && <AlertTriangle className="h-3.5 w-3.5 flex-none" />}
          {n.title}
        </b>
        <span className="mt-0.5 block text-[12px] text-fg-2 md:text-[12.5px]">{n.message}</span>
        {category && <span className="mt-0.5 block text-[11px] text-fg-3">{category}</span>}
      </span>
      <span className="num flex-none whitespace-nowrap text-[11px] text-fg-3">
        {noticeTime(toDate(n.createdAt), now)}
      </span>
    </button>
  );
}

/** Every notification, newest first, from ListNotifications. Opening one marks it read. */
export default function NotificationsPage() {
  const history = useNotificationsStore((s) => s.history);
  const unreadCount = useNotificationsStore((s) => s.unreadCount);
  const fetchHistory = useNotificationsStore((s) => s.fetchHistory);
  const fetchMoreHistory = useNotificationsStore((s) => s.fetchMoreHistory);
  const markAsRead = useNotificationsStore((s) => s.markAsRead);
  const markAllAsRead = useNotificationsStore((s) => s.markAllAsRead);
  const filter: Filter = history.unreadOnly ? 'unread' : 'all';

  useEffect(() => {
    fetchHistory(false).catch(() => undefined);
  }, [fetchHistory]);

  const now = new Date();
  const firstLoad = history.loading && history.items.length === 0;
  const visible = history.unreadOnly ? history.items.filter((n) => !n.isRead) : history.items;

  return (
    <div className="page max-w-[760px]">
      <Link
        to="/dashboard"
        className="mb-2 inline-flex items-center gap-0.5 text-[13px] text-accent hover:underline md:hidden"
      >
        <ChevronLeft className="h-4 w-4" />
        Home
      </Link>
      <div className="mb-3 flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="m-0 text-[27px] leading-tight md:text-[21px]">Notifications</h1>
          <div className="mt-[3px] text-[12.5px] text-fg-3">
            {unreadCount > 0 ? `${unreadCount} unread` : 'All read'} ·{' '}
            <Link to="/settings/notifications" className="text-accent hover:underline">
              Choose what reaches you by email
            </Link>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <Segmented
            label="Show"
            value={filter}
            onChange={(f) => {
              fetchHistory(f === 'unread').catch(() => undefined);
            }}
            options={[
              { key: 'all', label: 'All' },
              { key: 'unread', label: 'Unread' },
            ]}
          />
          <button
            type="button"
            className="btn btn-secondary btn-sm"
            disabled={unreadCount === 0}
            onClick={() => {
              markAllAsRead().catch(() => undefined);
            }}
          >
            Mark all read
          </button>
        </div>
      </div>

      <section className="panel overflow-hidden">
        {firstLoad ? (
          <SkeletonRows rows={6} cols={2} />
        ) : history.error && history.items.length === 0 ? (
          <PanelError
            title="Notifications couldn't be loaded"
            cause={asSentence(history.error)}
            unaffected="Sessions keep running, and critical notices still go to your email."
            onRetry={() => {
              fetchHistory(history.unreadOnly).catch(() => undefined);
            }}
          />
        ) : visible.length === 0 ? (
          <EmptyState
            icon={Bell}
            title={history.unreadOnly ? 'Nothing unread' : 'Nothing yet'}
            body={
              history.unreadOnly
                ? "You've read everything. Switch to All to see past notices."
                : 'Fills, finished backtests and anything that needs a look will show here.'
            }
          />
        ) : (
          groupByDay(visible, now).map((g) => (
            <div key={g.label}>
              <div className="border-b border-line bg-sunk px-3.5 py-[5px] text-[11px] text-fg-3 md:px-4">
                {g.label}
              </div>
              {g.items.map((n) => (
                <NoticeRow
                  key={n.id}
                  n={n}
                  now={now}
                  onRead={() => {
                    if (!n.isRead) markAsRead(n.id).catch(() => undefined);
                  }}
                />
              ))}
            </div>
          ))
        )}
      </section>

      {history.error && history.items.length > 0 && (
        <p role="alert" className="mt-2 text-xs text-risk">
          The next page couldn&apos;t be loaded. {history.error}
        </p>
      )}
      {history.hasMore && (
        <div className="mt-3 flex justify-center">
          <button
            type="button"
            className="btn btn-secondary"
            disabled={history.loading}
            onClick={() => {
              fetchMoreHistory().catch(() => undefined);
            }}
          >
            {history.loading
              ? 'Loading…'
              : `Show older (${history.items.length} of ${history.total})`}
          </button>
        </div>
      )}
    </div>
  );
}
