import React, { useState, useEffect } from 'react';
import { 
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend
} from 'recharts';
import DashboardCard from '../components/DashboardCard';
import TournamentFilter from '../components/TournamentFilter';
import useDataLoader from '../hooks/useDataLoader';

const TeamAnalysis = () => {
  const { data, loading, error, selectedTournaments, handleTournamentSelection, handleSelectAllTournaments } = useDataLoader();
  const [teamStats, setTeamStats] = useState([]);
  
  // Process team data when data or selected tournaments change
  useEffect(() => {
    if (!data || !data.historical) return;
    
    // Get team stats from the historical data
    // Group players by team and calculate team statistics
    const teams = {};
    data.historical.forEach(player => {
      if (!player.name) return;
      
      // Use full player name as we don't have team information
      const playerName = player.name;
      
      // Create an entry for this player as an individual "team"
      if (!teams[playerName]) {
        teams[playerName] = {
          name: playerName,
          games: player.games || 0,
          wins: player.victories || 0,
          draws: player.draws || 0,
          losses: player.defeats || 0,
          points: player.points || 0,
          goalDiff: 0 // We don't have this data in historical
        };
      }
    });
    
    // Convert teams object to array
    const teamsArray = Object.values(teams);
    
    // Sort teams by points
    const sortedTeams = [...teamsArray].sort((a, b) => b.points - a.points);
    
    setTeamStats(sortedTeams);
  }, [data, selectedTournaments]);
  
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500 mx-auto"></div>
          <p className="mt-4 text-xl font-semibold text-gray-700">Loading team data...</p>
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
  
  // Prepare win rate data for the chart
  const winRateData = teamStats.map(team => ({
    team: team.name,
    winRate: team.games > 0 ? Math.round((team.wins / team.games) * 100) : 0
  }));
  
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow p-6">
        <h1 className="text-2xl font-bold mb-2">Team Analysis</h1>
        <p className="text-gray-600">Comprehensive analysis of team performance and statistics</p>
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
      
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <DashboardCard title="Team Performance">
          {teamStats.length > 0 ? (
            <div className="overflow-x-auto">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Player</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">GP</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">W</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">D</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">L</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Pts</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {teamStats.map((team, index) => (
                    <tr key={index}>
                      <td className="px-4 py-3 whitespace-nowrap font-medium">{team.name}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{team.games}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{team.wins}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{team.draws}</td>
                      <td className="px-4 py-3 whitespace-nowrap">{team.losses}</td>
                      <td className="px-4 py-3 whitespace-nowrap font-bold">{team.points}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="text-center p-6 text-gray-500">
              No team data available for the selected tournaments
            </div>
          )}
        </DashboardCard>

        <DashboardCard title="Team Win Rates">
          {winRateData.length > 0 ? (
            <div className="h-80">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={winRateData}
                  margin={{ top: 20, right: 30, left: 20, bottom: 40 }}
                >
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="team" angle={-45} textAnchor="end" />
                  <YAxis label={{ value: 'Win Rate (%)', angle: -90, position: 'insideLeft' }} />
                  <Tooltip formatter={(value) => [`${value}%`, 'Win Rate']} />
                  <Bar dataKey="winRate" fill="#3b82f6" name="Win Rate" />
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="text-center p-6 text-gray-500">
              No team data available for the selected tournaments
            </div>
          )}
        </DashboardCard>
      </div>
    </div>
  );
};

export default TeamAnalysis; 