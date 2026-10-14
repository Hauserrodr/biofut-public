import React from 'react';
import { 
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  PieChart, Pie, Cell
} from 'recharts';
import DashboardCard from '../components/DashboardCard';
import TournamentFilter from '../components/TournamentFilter';
import useDataLoader from '../hooks/useDataLoader';
import { getTopPlayers } from '../services/dataService';

const Rankings = () => {
  const { 
    data, 
    loading, 
    error, 
    selectedTournaments, 
    handleTournamentSelection, 
    handleSelectAllTournaments 
  } = useDataLoader();
  
  // Colors for charts
  const COLORS = ['#0088FE', '#00C49F', '#FFBB28', '#FF8042', '#8884d8'];
  
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500 mx-auto"></div>
          <p className="mt-4 text-xl font-semibold text-gray-700">Loading rankings data...</p>
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
  
  // Get top players based on different criteria, passing selected tournaments
  const topGoalscorers = getTopPlayers('goals', 5, selectedTournaments);
  const topWinRates = getTopPlayers('wins', 5, selectedTournaments);
  const topPoints = getTopPlayers('points', 10, selectedTournaments);
  
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold mb-2">Player Rankings</h1>
        <p className="text-gray-600">Comprehensive rankings of all players based on various metrics</p>
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
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <DashboardCard title="Top Goalscorers">
          {topGoalscorers.length > 0 ? (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={topGoalscorers}
                  layout="vertical"
                  margin={{ top: 5, right: 30, left: 60, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis dataKey="name" type="category" />
                  <Tooltip formatter={(value) => [value, 'Goals']} />
                  <Legend />
                  <Bar dataKey="value" fill="#3b82f6" name="Goals" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="text-center p-6 text-gray-500">
              No goal data available for the selected tournaments
            </div>
          )}
        </DashboardCard>

        <DashboardCard title="Top Win Rates">
          {topWinRates.length > 0 ? (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={topWinRates}
                  layout="vertical"
                  margin={{ top: 5, right: 30, left: 60, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis type="number" />
                  <YAxis dataKey="name" type="category" />
                  <Tooltip formatter={(value) => [value, 'Wins']} />
                  <Legend />
                  <Bar dataKey="value" fill="#10b981" name="Wins" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="text-center p-6 text-gray-500">
              No win data available for the selected tournaments
            </div>
          )}
        </DashboardCard>
      </div>
      
      <DashboardCard title="Points Leaderboard">
        {data?.players && data.players.length > 0 ? (
          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-gray-200">
              <thead className="bg-gray-50">
                <tr>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Rank</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Player</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Points</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Games</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Wins</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Draws</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Losses</th>
                  <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Win Rate</th>
                </tr>
              </thead>
              <tbody className="bg-white divide-y divide-gray-200">
                {data.players
                  .sort((a, b) => b.points - a.points)
                  .slice(0, 10)
                  .map((player, index) => (
                    <tr key={index}>
                      <td className="px-4 py-3 whitespace-nowrap font-bold">{index + 1}</td>
                      <td className="px-4 py-3 whitespace-nowrap font-medium">{player.name}</td>
                      <td className="px-4 py-3 whitespace-nowrap font-bold">{player.points}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{player.games}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{player.wins}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{player.draws}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{player.losses}</td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        {player.winRate}%
                      </td>
                    </tr>
                  ))}
              </tbody>
            </table>
          </div>
        ) : (
          <div className="text-center p-6 text-gray-500">
            No player data available for the selected tournaments
          </div>
        )}
      </DashboardCard>
      
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <DashboardCard title="Points Distribution">
          {topPoints.length > 0 ? (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={topPoints}
                    cx="50%"
                    cy="50%"
                    labelLine={true}
                    label={({ name, value }) => `${name} (${value})`}
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="value"
                    nameKey="name"
                  >
                    {topPoints.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip formatter={(value, name) => [`${value} points`, name]} />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="text-center p-6 text-gray-500">
              No points data available for the selected tournaments
            </div>
          )}
        </DashboardCard>
      </div>
    </div>
  );
};

export default Rankings; 