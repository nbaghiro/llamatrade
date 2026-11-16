import { Outlet } from 'react-router-dom';

import NewStrategyDialog from '../../components/strategies/NewStrategyDialog';
import StrategyPreviewDialog from '../../components/strategies/StrategyPreviewDialog';
import { useOnline } from '../../hooks/useOnline';
import { useUIStore } from '../../store/ui';
import { AgentFAB } from '../agent/AgentFAB';
import { CopilotSidePanel } from '../agent/CopilotSidePanel';
import { CommandPalette } from '../shell/CommandPalette';
import { MobileTabBar } from '../shell/MobileTabBar';
import { TopBar } from '../shell/TopBar';
import { useCommandPaletteShortcut } from '../shell/usePalette';
import { OfflineBanner } from '../states/OfflineBanner';

export default function Layout() {
  const newStrategyDialogOpen = useUIStore((s) => s.newStrategyDialogOpen);
  const closeNewStrategyDialog = useUIStore((s) => s.closeNewStrategyDialog);
  const { online } = useOnline();
  useCommandPaletteShortcut();

  return (
    <div className="min-h-screen bg-canvas text-fg">
      <a
        href="#main"
        className="sr-only z-50 rounded-[7px] border border-line-strong bg-panel text-[13px] font-medium text-fg shadow-lg focus:not-sr-only focus:fixed focus:left-3 focus:top-2.5 focus:px-3 focus:py-2"
      >
        Skip to content
      </a>
      <TopBar />
      <OfflineBanner />

      <main
        id="main"
        tabIndex={-1}
        className={`overflow-x-clip pb-[84px] outline-none transition-opacity focus-visible:[box-shadow:none] md:pb-0 ${online ? '' : 'opacity-[0.72]'}`}
      >
        <Outlet />
      </main>

      <MobileTabBar />
      <CommandPalette />

      <AgentFAB />
      <CopilotSidePanel />
      <NewStrategyDialog isOpen={newStrategyDialogOpen} onClose={closeNewStrategyDialog} />
      <StrategyPreviewDialog />
    </div>
  );
}
