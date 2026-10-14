import React, { useState, useEffect } from 'react';
import { 
  ResponsiveContainer, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis, Legend
} from 'recharts';
import DashboardCard from '../components/DashboardCard';
import TournamentFilter from '../components/TournamentFilter';
import useDataLoader from '../hooks/useDataLoader';
import { getPlayerStats } from '../services/dataService';

const PlayerStats = () => {
  const { 
    data, 
    loading, 
    error, 
    selectedTournaments, 
    handleTournamentSelection, 
    handleSelectAllTournaments 
  } = useDataLoader();
  
  const [selectedPlayer, setSelectedPlayer] = useState('');
  
  // Get player list from data
  const playerList = data?.players?.map(p => p.name) || [];
  
  // Set default selected player if none selected
  useEffect(() => {
    if (playerList.length > 0 && !selectedPlayer) {
      setSelectedPlayer(playerList[0]);
    }
  }, [playerList, selectedPlayer]);
  
  // Generate player performance chart data
  const getPlayerPerformanceData = (playerName) => {
    const stats = getPlayerStats(playerName, selectedTournaments);
    if (!stats) return [];
    
    return [
      { name: 'Goals', value: stats.goalsFor || 0 },
      { name: 'Assists', value: stats.assists || 0 },
      { name: 'Wins', value: stats.wins || 0 },
      { name: 'Draws', value: stats.draws || 0 },
      { name: 'Losses', value: stats.losses || 0 }
    ];
  };
  
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500 mx-auto"></div>
          <p className="mt-4 text-xl font-semibold text-gray-700">Loading player data...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <div className="text-center text-red-500">
          <p className="text-xl font-bold">Error</p>
          <p>{error}</p>
        </div>
      </div>
    );
  }
  
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold mb-2">Player Statistics</h1>
        <p className="text-gray-600">Detailed analysis of individual player performance</p>
      </div>
      
      {/* Tournament Filter */}
      {data && (
        <TournamentFilter
          tournaments={data}
          selectedTournaments={selectedTournaments}
          onTournamentSelect={handleTournamentSelection}
          onSelectAll={handleSelectAllTournaments}
        />
      )}
      
      <DashboardCard title="Player Performance">
        <div className="mb-6">
          <label className="block text-sm font-medium text-gray-700 mb-2">Select Player</label>
          <select 
            className="border border-gray-300 rounded-md py-2 px-4 w-full max-w-md"
            value={selectedPlayer}
            onChange={(e) => setSelectedPlayer(e.target.value)}
          >
            {playerList.length > 0 ? (
              playerList.map(player => (
                <option key={player} value={player}>{player}</option>
              ))
            ) : (
              <option value="">No players available</option>
            )}
          </select>
        </div>

        {selectedPlayer && (
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
            <div>
              <h3 className="text-xl font-semibold mb-4">Stats Summary</h3>
              <div className="bg-gray-50 p-4 rounded-lg">
                {(() => {
                  const stats = getPlayerStats(selectedPlayer, selectedTournaments);
                  if (!stats) return <p>No data available</p>;
                  
                  return (
                    <div className="grid grid-cols-2 gap-4">
                      <div>
                        <p className="text-gray-500">Games</p>
                        <p className="text-2xl font-bold">{stats.games}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Points</p>
                        <p className="text-2xl font-bold">{stats.points}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Win Rate</p>
                        <p className="text-2xl font-bold">{stats.winRate}%</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Goals</p>
                        <p className="text-2xl font-bold">{stats.goalsFor || 0}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Assists</p>
                        <p className="text-2xl font-bold">{stats.assists || 0}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Goals/Game</p>
                        <p className="text-2xl font-bold">{stats.goalsPerGame || 0}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Record (W-D-L)</p>
                        <p className="text-xl font-bold">{stats.wins}-{stats.draws}-{stats.losses}</p>
                      </div>
                      <div>
                        <p className="text-gray-500">Effectiveness</p>
                        <p className="text-2xl font-bold">{stats.effectiveness || 0}%</p>
                      </div>
                    </div>
                  );
                })()}
              </div>
            </div>
            
            <div>
              <h3 className="text-xl font-semibold mb-4">Performance Chart</h3>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <RadarChart outerRadius={90} data={getPlayerPerformanceData(selectedPlayer)}>
                    <PolarGrid />
                    <PolarAngleAxis dataKey="name" />
                    <PolarRadiusAxis />
                    <Radar name={selectedPlayer} dataKey="value" stroke="#8884d8" fill="#8884d8" fillOpacity={0.6} />
                    <Legend />
                  </RadarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>
        )}
      </DashboardCard>
      
      <DashboardCard title="Recent Form">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Player</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Last 5 Games</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Win Rate</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Goals</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Assists</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {data?.players ? (
                data.players.slice(0, 10).map((player, index) => {
                  const stats = getPlayerStats(player.name, selectedTournaments);
                  if (!stats) return null;
                  
                  // Generate recent form data based on win rate
                  const winRate = stats.winRate || 0;
                  let recentForm = [];
                  
                  // Simple algorithm to generate mock form based on win rate
                  for (let i = 0; i < 5; i++) {
                    if (Math.random() * 100 < winRate) {
                      recentForm.push('V');
                    } else if (Math.random() * 100 < 50) {
                      recentForm.push('E');
                    } else {
                      recentForm.push('D');
                    }
                  }
                  
                  return (
                    <tr key={index} className={player.name === selectedPlayer ? 'bg-blue-50' : ''}>
                      <td className="px-6 py-4 whitespace-nowrap font-medium">{player.name}</td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        <div className="flex space-x-1">
                          {recentForm.map((result, idx) => (
                            <span 
                              key={idx} 
                              className={`w-6 h-6 flex items-center justify-center rounded-full text-xs font-medium ${
                                result === 'V' ? 'bg-green-100 text-green-800' : 
                                result === 'E' ? 'bg-yellow-100 text-yellow-800' : 
                                result === 'D' ? 'bg-red-100 text-red-800' : 'bg-gray-100 text-gray-800'
                              }`}
                            >
                              {result || '-'}
                            </span>
                          ))}
                        </div>
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">
                        {stats.winRate}%
                      </td>
                      <td className="px-6 py-4 whitespace-nowrap">{stats.goalsFor || 0}</td>
                      <td className="px-6 py-4 whitespace-nowrap">{stats.assists || 0}</td>
                    </tr>
                  );
                })
              ) : (
                <tr>
                  <td className="px-6 py-4 whitespace-nowrap" colSpan={5}>
                    No player data available
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </DashboardCard>
    </div>
  );
};

export default PlayerStats; 