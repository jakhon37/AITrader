import { Routes, Route } from 'react-router-dom';
import { Sidebar } from './components/Layout/Sidebar';
import { TradingTerminal } from './components/Layout/TradingTerminal';
import { ReplayPage } from './components/Replay/ReplayPage';
import { useWebSocket } from './hooks/useWebSocket';

export default function App() {
  useWebSocket();

  return (
    <div className="terminal-layout">
      <Sidebar />
      <main style={{ overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        <Routes>
          <Route path="/" element={<TradingTerminal />} />
          <Route path="/replay" element={<ReplayPage />} />
        </Routes>
      </main>
    </div>
  );
}
