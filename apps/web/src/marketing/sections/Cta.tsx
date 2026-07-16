import { WaitlistForm } from '../components/WaitlistForm';

/** Big closing CTA with the "Join the beta" waitlist form. */
export function Cta() {
  return (
    <section className="cta" id="join">
      <div className="wrap">
        <span className="kicker" style={{ color: 'var(--orange)', marginBottom: 22 }}>
          Closed beta · Invite only
        </span>
        <h2>
          STOP <span className="outline">GUESSING.</span>
          <br />
          START <span className="o">TESTING.</span>
        </h2>
        <p>
          Build a strategy, prove it against years of history, rehearse it risk-free in paper, then
          go live on your own account with real money — all in one open-source machine.
        </p>
        <WaitlistForm />
      </div>
    </section>
  );
}
