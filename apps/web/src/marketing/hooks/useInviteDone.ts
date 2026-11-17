import { useCallback, useEffect, useState } from 'react';

import { INVITE_DONE_KEY } from '../lib/invite';

const DONE_EVENT = 'lt-waitlist-done';

function read(): boolean {
  try {
    return window.localStorage.getItem(INVITE_DONE_KEY) === '1';
  } catch {
    return false;
  }
}

/** Whether this browser has joined the waitlist; shared by every invite form and the nav. */
export function useInviteDone(): [boolean, () => void] {
  const [done, setDone] = useState(read);
  useEffect(() => {
    const sync = () => setDone(read());
    const onStorage = (e: StorageEvent) => {
      if (e.key === INVITE_DONE_KEY || e.key === null) sync();
    };
    window.addEventListener('storage', onStorage);
    window.addEventListener(DONE_EVENT, sync);
    return () => {
      window.removeEventListener('storage', onStorage);
      window.removeEventListener(DONE_EVENT, sync);
    };
  }, []);
  const markDone = useCallback(() => {
    try {
      window.localStorage.setItem(INVITE_DONE_KEY, '1');
    } catch {
      /* storage unavailable: the confirmation still shows for this visit */
    }
    setDone(true);
    window.dispatchEvent(new Event(DONE_EVENT));
  }, []);
  return [done, markDone];
}
