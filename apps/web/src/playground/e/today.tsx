import { useMemo, useState } from 'react';

import { ACCOUNT } from '../data';

import { useAsk } from './askContext';
import { Page, PageHead } from './frame';
import { PROPOSALS } from './model';
import { ACCOUNT_COLS, accountRows } from './rows';
import { ACCOUNT_SCOPE, type Scope } from './scope';
import { ScopeSheet } from './sheet';
import { LedgerTree } from './tree';
import { Foot } from './ui';

export function Today() {
  const { proposals, setProposal } = useAsk();
  const rows = useMemo(
    () => accountRows({ proposals, setProposal }, { root: true }),
    [proposals, setProposal]
  );
  const [scope, setScope] = useState<Scope>(ACCOUNT_SCOPE);
  const waiting = Object.keys(PROPOSALS).filter((id) => (proposals[id] ?? 'open') === 'open');
  return (
    <Page ask={false}>
      <PageHead
        eyebrow="Friday, November 20 · 12:04 ET"
        title="Today"
        meta={
          <>
            Down ${Math.abs(ACCOUNT.today).toFixed(2)} so far
            {waiting.length > 0 &&
              ` · ${waiting.length} Copilot ${waiting.length === 1 ? 'edit' : 'edits'} waiting in the tree`}
            {' · Momentum Sectors rebalances Nov 23'}
          </>
        }
      />
      <ScopeSheet scope={scope}>
        <LedgerTree
          label="Account"
          name="Account"
          rows={rows}
          cols={ACCOUNT_COLS}
          selected={scope.key}
          onSelect={(r) => r.scope && setScope(r.scope)}
        />
      </ScopeSheet>
      <Foot
        items={[
          'Select a row to scope the chart and Ask to it',
          'double-click to open',
          'prices Nov 20, 2026, 12:04 ET',
          'history before Nov 19 is sample data',
        ]}
      />
    </Page>
  );
}
