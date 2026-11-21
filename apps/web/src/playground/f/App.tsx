import { Route, Routes } from 'react-router-dom';

import { BacktestPage, BacktestsList } from './backtests';
import { CopilotProvider } from './copilot';
import { StatusBar, TopBar } from './frame';
import { Portfolio } from './portfolio';
import { SessionPage, SessionsList } from './sessions';
import { StrategiesList, StrategyPage } from './strategies';
import { Today } from './today';

/** Option F: a calm terminal. Dense 32px rows on one grid, and a command bar that asks, jumps and runs. */
export default function App() {
  return (
    <CopilotProvider>
      <div className="min-h-screen bg-canvas text-fg antialiased">
        <TopBar />
        <Routes>
          <Route index element={<Today />} />
          <Route path="strategies" element={<StrategiesList />} />
          <Route path="strategies/:id" element={<StrategyPage />} />
          <Route path="backtests" element={<BacktestsList />} />
          <Route path="backtests/:id" element={<BacktestPage />} />
          <Route path="sessions" element={<SessionsList />} />
          <Route path="sessions/:id" element={<SessionPage />} />
          <Route path="portfolio" element={<Portfolio />} />
          <Route path="*" element={<Today />} />
        </Routes>
        <StatusBar />
      </div>
    </CopilotProvider>
  );
}
