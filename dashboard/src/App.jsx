import { BrowserRouter as Router, Routes, Route } from 'react-router-dom';
import Layout from './components/Layout';
import Dashboard from './pages/Dashboard';
import PlayerStats from './pages/PlayerStats';
import TeamAnalysis from './pages/TeamAnalysis';
import Performance from './pages/Performance';
import Rankings from './pages/Rankings';
import Settings from './pages/Settings';

function App() {
  return (
    <Router>
      <Layout>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/players" element={<PlayerStats />} />
          <Route path="/teams" element={<TeamAnalysis />} />
          <Route path="/performance" element={<Performance />} />
          <Route path="/rankings" element={<Rankings />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </Layout>
    </Router>
  );
}

export default App;
