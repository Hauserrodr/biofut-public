import React from 'react';
import { 
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend,
  PieChart, Pie, Cell
} from 'recharts';
import DashboardCard from '../components/DashboardCard';
import TournamentFilter from '../components/TournamentFilter';
import useDataLoader from '../hooks/useDataLoader';
import { getTopPlayers } from '../services/dataService';
import bdsmLogo from '../assets/bdsm-logo.svg';

const Dashboard = () => {
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
          <p className="mt-4 text-xl font-semibold text-gray-700">Loading BIOFUT data...</p>
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
  
  // Calculate total matches from historical data (if available)
  const totalMatches = data?.historical && Array.isArray(data.historical) 
    ? data.historical.reduce((total, player) => total + (player.games || 0), 0) / 2 // Divide by 2 as each match has 2 players
    : 0;
  
  // Calculate total players from players array (more accurate than using database length)
  const totalPlayers = data?.players && Array.isArray(data.players) 
    ? data.players.length 
    : 0;
  
  // Calculate number of tournaments
  const totalTournaments = data?.tournaments && typeof data.tournaments === 'object'
    ? Object.keys(data.tournaments).length
    : 0;
  
  // Points Leaders component with error handling
  const renderPointsLeadersChart = () => {
    const pointsData = getTopPlayers('points', 5, selectedTournaments);
    
    if (!pointsData || pointsData.length === 0) {
      return (
        <div className="h-80 flex items-center justify-center">
          <p className="text-gray-500">No data available</p>
        </div>
      );
    }
    
    return (
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <PieChart>
            <Pie
              data={pointsData}
              nameKey="name"
              dataKey="value"
              cx="50%"
              cy="50%"
              outerRadius={80}
              label={({name, value}) => `${name} (${value})`}
            >
              {pointsData.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={COLORS[index % COLORS.length]} />
              ))}
            </Pie>
            <Tooltip formatter={(value, name, props) => [`${value} points`, props.payload.name]} />
            <Legend />
          </PieChart>
        </ResponsiveContainer>
      </div>
    );
  };
  
  // Top Goalscorers component with error handling
  const renderTopGoalscorersChart = () => {
    const goalsData = getTopPlayers('goals', 5, selectedTournaments);
    
    if (!goalsData || goalsData.length === 0) {
      return (
        <div className="h-80 flex items-center justify-center">
          <p className="text-gray-500">No data available</p>
        </div>
      );
    }
    
    return (
      <div className="h-80">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={goalsData}
            layout="vertical"
            margin={{ top: 5, right: 30, left: 60, bottom: 5 }}
          >
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis type="number" />
            <YAxis dataKey="name" type="category" />
            <Tooltip />
            <Legend />
            <Bar dataKey="value" fill="#8884d8" name="Goals" />
          </BarChart>
        </ResponsiveContainer>
      </div>
    );
  };
  
  // Recent Activity table component
  const renderRecentActivity = (data) => {
    if (!data?.historical || data.historical.length === 0) {
      return (
        <tr>
          <td className="px-6 py-4 whitespace-nowrap" colSpan={3}>
            No recent activity available
          </td>
        </tr>
      );
    }

    // Get the most recent matches (up to 3)
    return data.historical.slice(0, 3).map((match, index) => (
      <tr key={index}>
        <td className="px-6 py-4 whitespace-nowrap">
          {typeof match.date === 'string' ? match.date : 'N/A'}
        </td>
        <td className="px-6 py-4 whitespace-nowrap">Match Completed</td>
        <td className="px-6 py-4 whitespace-nowrap">
          {typeof match.player1 === 'string' ? match.player1 : 
           typeof match.name === 'string' ? match.name : 'Player 1'} 
          vs 
          {typeof match.player2 === 'string' ? ` ${match.player2}` : ' Player 2'}
          {match.goals1 !== undefined && match.goals2 !== undefined && 
            ` (${match.goals1}-${match.goals2})`
          }
        </td>
      </tr>
    ));
  };
  
  return (
    <div className="space-y-6">
      <div className="bg-white rounded-lg shadow p-6">
        <div className="flex items-center gap-4">
          <img src={bdsmLogo} alt="BDSM Logo" className="h-16 w-16" />
          <div>
            <h1 className="text-2xl font-bold mb-1">BIOFUT Analytics Dashboard</h1>
            <p className="text-gray-600">BioFut Department of Statistical Magic (BDSM)</p>
          </div>
        </div>
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
      
      {/* Dashboard Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <DashboardCard title="Total Players">
          <div className="text-center">
            <p className="text-4xl font-bold text-primary-main">
              {totalPlayers}
            </p>
            <p className="text-gray-500 mt-2">Registered players</p>
          </div>
        </DashboardCard>
        
        <DashboardCard title="Total Tournaments">
          <div className="text-center">
            <p className="text-4xl font-bold text-primary-main">
              {totalTournaments}
            </p>
            <p className="text-gray-500 mt-2">Tournaments tracked</p>
          </div>
        </DashboardCard>
        
        <DashboardCard title="Total Matches">
          <div className="text-center">
            <p className="text-4xl font-bold text-primary-main">
              {totalMatches}
            </p>
            <p className="text-gray-500 mt-2">Matches played</p>
          </div>
        </DashboardCard>
      </div>
      
      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <DashboardCard title="Top Goalscorers">
          {renderTopGoalscorersChart()}
        </DashboardCard>
        
        <DashboardCard title="Points Leaders">
          {renderPointsLeadersChart()}
        </DashboardCard>
      </div>
      
      {/* Recent Activity */}
      <DashboardCard title="Recent Activity">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Date</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Event</th>
                <th className="px-6 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Details</th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {renderRecentActivity(data)}
            </tbody>
          </table>
        </div>
      </DashboardCard>
    </div>
  );
};

export default Dashboard; 