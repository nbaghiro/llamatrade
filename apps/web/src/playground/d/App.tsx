import { Route, Routes } from 'react-router-dom';

import { AskProvider } from './ask';
import { BacktestPage, BacktestsList } from './backtests';
import { TopBar } from './frame';
import { Portfolio } from './portfolio';
import { SessionPage, SessionsList } from './sessions';
import { StrategiesList, StrategyPage } from './strategies';
import { Today } from './today';

/** Option D: one continuous page, with Ask as the hero and its answers written into the page. */
export default function App() {
  return (
    <AskProvider>
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
      </div>
    </AskProvider>
  );
}
