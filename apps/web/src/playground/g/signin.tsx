import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { ExampleBacktestPanel } from '../../components/auth/ExampleBacktestPanel';
import { AlpacaButton, Field, FormFoot, LINK, OrDivider } from '../../components/auth/fields';

import { StageCard } from './ui';

/** The sign-in form, the same one the app grew out of. Signing in carries on into Today. */
export function SignInLeft() {
  const nav = useNavigate();
  const [email, setEmail] = useState('naib@llamatrade.dev');
  const [password, setPassword] = useState('demo-password');
  return (
    <div className="mx-auto grid w-full max-w-[340px] gap-3.5 pt-[12vh]">
      <header>
        <h1 className="m-0 text-[22px] font-semibold leading-tight tracking-[-0.02em]">Sign in</h1>
        <p className="mb-0 mt-[5px] text-[13px] text-fg-2">Welcome back to LlamaTrade.</p>
      </header>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          nav('/g');
        }}
        className="grid gap-3.5"
      >
        <Field
          id="g-email"
          label="Email address"
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
        />
        <Field
          id="g-password"
          label="Password"
          aside={<span className={LINK}>Forgot password?</span>}
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
        />
        <button type="submit" className="btn btn-primary btn-lg w-full">
          Sign in
        </button>
      </form>
      <OrDivider />
      <AlpacaButton label="Continue with Alpaca" onClick={() => nav('/g')} />
      <FormFoot>
        New here? <span className={LINK}>Request an invite</span>
      </FormFoot>
    </div>
  );
}

export function SignInStage() {
  return (
    <StageCard>
      <ExampleBacktestPanel />
    </StageCard>
  );
}
