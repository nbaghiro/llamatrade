import { Redirect, useLocalSearchParams } from 'expo-router';
import { useEffect } from 'react';

import { openCopilot } from '../../src/copilot/store';
import type { CopilotContext } from '../../src/copilot/subjects';

const KINDS: readonly CopilotContext['kind'][] = ['session', 'strategy', 'account', 'marker'];

/** A link into Copilot about a subject (`/copilot/open?kind=session&id=…&q=…`): opens the half sheet over Home. */
export default function OpenCopilot() {
  const { kind, id, date, q } = useLocalSearchParams<{ kind?: string; id?: string; date?: string; q?: string }>();
  useEffect(() => {
    const k = KINDS.find((x) => x === kind) ?? 'account';
    openCopilot({ kind: k, id: id ?? 'account', date }, { question: q });
  }, [kind, id, date, q]);
  return <Redirect href="/(tabs)" />;
}
