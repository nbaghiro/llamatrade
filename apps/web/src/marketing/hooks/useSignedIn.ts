import { useEffect, useState } from 'react';

import { AUTH_STORAGE_KEY, readSignedIn } from '../lib/session';

function read(): boolean {
  try {
    return readSignedIn(window.localStorage.getItem(AUTH_STORAGE_KEY));
  } catch {
    return false;
  }
}

/** Whether the visitor is signed in to the app; follows sign-in and sign-out in other tabs. */
export function useSignedIn(): boolean {
  const [signedIn, setSignedIn] = useState(read);
  useEffect(() => {
    const sync = (e: StorageEvent) => {
      if (e.key === AUTH_STORAGE_KEY || e.key === null) setSignedIn(read());
    };
    window.addEventListener('storage', sync);
    return () => window.removeEventListener('storage', sync);
  }, []);
  return signedIn;
}
