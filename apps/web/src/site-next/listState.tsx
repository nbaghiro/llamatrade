import { Check } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { InviteForm } from '../marketing/components/InviteForm';
import { useInviteDone } from '../marketing/hooks/useInviteDone';
import { INVITE_COPY } from '../marketing/lib/invite';

/** True only on the visit where the person joined, so a confirmation can show once. */
function useJustJoined(done: boolean): boolean {
  const was = useRef(done);
  const [just, setJust] = useState(false);
  useEffect(() => {
    if (done && !was.current) setJust(true);
    if (!done) setJust(false);
    was.current = done;
  }, [done]);
  return just;
}

function OnceConfirm() {
  const [phase, setPhase] = useState<'show' | 'fade' | 'gone'>('show');
  useEffect(() => {
    const a = window.setTimeout(() => setPhase('fade'), 3200);
    const b = window.setTimeout(() => setPhase('gone'), 3900);
    return () => {
      window.clearTimeout(a);
      window.clearTimeout(b);
    };
  }, []);
  if (phase === 'gone') return null;
  return (
    <div className="mt-8 w-full">
      <div
        className={`transition-[opacity,transform] duration-700 ${
          phase === 'fade' ? '-translate-y-1 opacity-0' : 'opacity-100'
        }`}
      >
        <div className="invite-ok" role="status">
          <span className="tick" aria-hidden="true">
            <Check size={15} strokeWidth={2.25} />
          </span>
          {INVITE_COPY.done}
        </div>
      </div>
    </div>
  );
}

/**
 * The hero's invite slot: the form until someone joins, the confirmation once on that visit, then
 * nothing, since the nav's "On the list" carries the state.
 */
export function HeroInvite() {
  const [done] = useInviteDone();
  const just = useJustJoined(done);
  if (!done) {
    return (
      <div className="mt-8 w-full">
        <InviteForm id="hero-invite" />
      </div>
    );
  }
  return just ? <OnceConfirm /> : null;
}
