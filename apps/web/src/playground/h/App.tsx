import { Route, Routes } from 'react-router-dom';

import { AskProvider } from './ask';
import { BacktestPage, BacktestsList } from './backtests';
import { Masthead } from './frame';
import { Portfolio } from './portfolio';
import { SessionPage, SessionsList } from './sessions';
import { StrategiesList, StrategyPage } from './strategies';
import { useSerifFont } from './style';
import { Today } from './today';

/** Option H: the account as a financial paper, with Today as its front page. */
export default function App() {
  useSerifFont();
  return (
    <AskProvider>
      <div className="min-h-screen bg-canvas text-fg antialiased">
        <Masthead />
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
