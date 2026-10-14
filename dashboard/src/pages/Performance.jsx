import React, { useState, useEffect } from 'react';
import DashboardCard from '../components/DashboardCard';
import TournamentFilter from '../components/TournamentFilter';
import useDataLoader from '../hooks/useDataLoader';
import { getPlayerStats, getOpponentMatchup } from '../services/dataService';

const Performance = () => {
  const { 
    data, 
    loading, 
    error, 
    selectedTournaments, 
    handleTournamentSelection, 
    handleSelectAllTournaments 
  } = useDataLoader();
  
  const [selectedPlayer, setSelectedPlayer] = useState('');
  const [selectedTeammate, setSelectedTeammate] = useState('');
  const [selectedOpponent, setSelectedOpponent] = useState('');
  const [teammateSynergy, setTeammateSynergy] = useState(null);
  const [playerMatchup, setPlayerMatchup] = useState(null);
  
  // Get player list from historical data
  const playerList = data?.players?.map(p => p.name) || [];
  
  // Set default selected players if none selected
  useEffect(() => {
    if (playerList.length > 0) {
      if (!selectedPlayer) {
        setSelectedPlayer(playerList[0]);
      }
      
      if (!selectedTeammate && playerList.length > 1) {
        setSelectedTeammate(playerList[1]);
      }
      
      if (!selectedOpponent && playerList.length > 2) {
        setSelectedOpponent(playerList[2]);
      }
    }
  }, [playerList, selectedPlayer, selectedTeammate, selectedOpponent]);
  
  // Calculate teammate synergy when players change
  useEffect(() => {
    if (selectedPlayer && selectedTeammate && selectedPlayer !== selectedTeammate) {
      calculateTeammateSynergy();
    }
  }, [selectedPlayer, selectedTeammate, selectedTournaments]);
  
  // Calculate opponent matchup when players change
  useEffect(() => {
    if (selectedPlayer && selectedOpponent && selectedPlayer !== selectedOpponent) {
      calculateOpponentMatchup();
    }
  }, [selectedPlayer, selectedOpponent, selectedTournaments]);
  
  // Calculate teammate synergy
  const calculateTeammateSynergy = () => {
    if (!selectedPlayer || !selectedTeammate || selectedPlayer === selectedTeammate) {
      setTeammateSynergy(null);
      return;
    }
    
    // Get individual stats for comparison
    const player1Stats = getPlayerStats(selectedPlayer, selectedTournaments);
    const player2Stats = getPlayerStats(selectedTeammate, selectedTournaments);
    
    if (!player1Stats || !player2Stats) {
      setTeammateSynergy(null);
      return;
    }
    
    // Get confronto data from the API
    const confrontos = data?.confrontos || [];
    
    // Look for matches where both players participated together
    let sharedMatches = 0;
    let sharedWins = 0;
    let sharedGoals = 0;
    
    // Process confrontos data if available
    if (Array.isArray(confrontos) && confrontos.length > 0) {
      confrontos.forEach(match => {
        if ((match.player1 === selectedPlayer && match.player2 === selectedTeammate) ||
            (match.player1 === selectedTeammate && match.player2 === selectedPlayer)) {
          sharedMatches += match.games || 0;
          sharedWins += match.wins || 0;
          sharedGoals += match.goals || 0;
        }
      });
    }
    
    // Calculate synergy level
    let winRate = sharedMatches > 0 ? (sharedWins / sharedMatches) * 100 : 0;
    let goalsPerGame = sharedMatches > 0 ? sharedGoals / sharedMatches : 0;
    
    let synergyLevel = "Low";
    if (winRate > 60) synergyLevel = "High";
    else if (winRate > 45) synergyLevel = "Medium";
    
    // If no shared matches found, make an estimation based on individual stats
    if (sharedMatches === 0) {
      sharedMatches = Math.min(player1Stats.games || 0, player2Stats.games || 0) / 3;
      const p1WinRate = player1Stats.games > 0 ? (player1Stats.wins / player1Stats.games) * 100 : 0;
      const p2WinRate = player2Stats.games > 0 ? (player2Stats.wins / player2Stats.games) * 100 : 0;
      winRate = (p1WinRate + p2WinRate) / 2;
      
      const p1GoalsPerGame = player1Stats.games > 0 ? (player1Stats.goalsFor / player1Stats.games) : 0;
      const p2GoalsPerGame = player2Stats.games > 0 ? (player2Stats.goalsFor / player2Stats.games) : 0;
      goalsPerGame = (p1GoalsPerGame + p2GoalsPerGame) / 2;
      
      if (winRate > 60) synergyLevel = "Potentially High";
      else if (winRate > 45) synergyLevel = "Potentially Medium";
      else synergyLevel = "Potentially Low";
    }
    
    setTeammateSynergy({
      player1: selectedPlayer,
      player2: selectedTeammate,
      gamesPlayed: Math.round(sharedMatches),
      winRate: winRate.toFixed(1),
      goalsPerGame: goalsPerGame.toFixed(1),
      synergy: synergyLevel
    });
  };
  
  // Calculate opponent matchup
  const calculateOpponentMatchup = () => {
    if (!selectedPlayer || !selectedOpponent || selectedPlayer === selectedOpponent) {
      setPlayerMatchup(null);
      return;
    }
    
    // Get matchup data from confrontos
    const confrontos = data?.confrontos || [];
    let matchup = null;
    
    // Find direct matchup data if available
    if (Array.isArray(confrontos) && confrontos.length > 0) {
      for (const confronto of confrontos) {
        if ((confronto.player1 === selectedPlayer && confronto.player2 === selectedOpponent) ||
            (confronto.player1 === selectedOpponent && confronto.player2 === selectedPlayer)) {
          
          let wins = 0;
          let losses = 0;
          let draws = 0;
          
          if (confronto.player1 === selectedPlayer) {
            wins = confronto.wins || 0;
            losses = confronto.losses || 0;
            draws = (confronto.games || 0) - wins - losses;
          } else {
            losses = confronto.wins || 0;
            wins = confronto.losses || 0;
            draws = (confronto.games || 0) - wins - losses;
          }
          
          matchup = {
            player: selectedPlayer,
            opponent: selectedOpponent,
            games: confronto.games || 0,
            wins: wins,
            draws: draws,
            losses: losses,
            winRate: confronto.games > 0 ? (wins / confronto.games * 100).toFixed(1) : "0.0"
          };
          break;
        }
      }
    }
    
    // If no direct matchup found, use individual stats to estimate
    if (!matchup) {
      const playerStats = getPlayerStats(selectedPlayer, selectedTournaments);
      const opponentStats = getPlayerStats(selectedOpponent, selectedTournaments);
      
      if (!playerStats || !opponentStats) {
        setPlayerMatchup(null);
        return;
      }
      
      // Estimate based on their individual performances
      const estimatedGames = Math.min(playerStats.games || 5, opponentStats.games || 5) / 2;
      
      // Compare win rates to estimate match results
      const playerWinRate = playerStats.games > 0 ? (playerStats.wins / playerStats.games) : 0.5;
      const opponentWinRate = opponentStats.games > 0 ? (opponentStats.wins / opponentStats.games) : 0.5;
      
      const winProbability = playerWinRate / (playerWinRate + opponentWinRate);
      const estimatedWins = Math.round(estimatedGames * winProbability);
      const estimatedLosses = Math.round(estimatedGames * (1 - winProbability));
      const estimatedDraws = Math.round(estimatedGames - estimatedWins - estimatedLosses);
      
      matchup = {
        player: selectedPlayer,
        opponent: selectedOpponent,
        games: estimatedGames,
        wins: estimatedWins,
        draws: estimatedDraws,
        losses: estimatedLosses,
        winRate: (winProbability * 100).toFixed(1),
        estimated: true
      };
    }
    
    setPlayerMatchup(matchup);
  };
  
  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-screen bg-gray-100">
        <div className="text-center">
          <div className="animate-spin rounded-full h-12 w-12 border-t-2 border-b-2 border-blue-500 mx-auto"></div>
          <p className="mt-4 text-xl font-semibold text-gray-700">Loading performance data...</p>
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
        <h1 className="text-2xl font-bold mb-2">Performance Calculators</h1>
        <p className="text-gray-600">Analyze player synergies and head-to-head matchups</p>
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
      
      {/* Teammate Synergy Calculator */}
      <DashboardCard title="Teammate Synergy Calculator">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Player 1</label>
              <select 
                className="border border-gray-300 rounded-md py-2 px-4 w-full"
                value={selectedPlayer}
                onChange={(e) => setSelectedPlayer(e.target.value)}
              >
                {playerList.map(player => (
                  <option key={player} value={player}>{player}</option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Player 2</label>
              <select 
                className="border border-gray-300 rounded-md py-2 px-4 w-full"
                value={selectedTeammate}
                onChange={(e) => setSelectedTeammate(e.target.value)}
              >
                {playerList.map(player => (
                  <option key={player} value={player}>{player}</option>
                ))}
              </select>
            </div>
            
            <button 
              className="bg-primary-main text-white px-4 py-2 rounded-md hover:bg-primary-dark transition-colors"
              onClick={calculateTeammateSynergy}
            >
              Calculate Synergy
            </button>
          </div>
          
          <div className="bg-gray-50 p-6 rounded-lg">
            {teammateSynergy ? (
              <div>
                <h3 className="text-lg font-semibold mb-4">Synergy Results</h3>
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Players:</span>
                    <span className="font-medium">{teammateSynergy.player1} & {teammateSynergy.player2}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Games Together:</span>
                    <span className="font-medium">{teammateSynergy.gamesPlayed}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Win Rate:</span>
                    <span className="font-medium">{teammateSynergy.winRate}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Goals Per Game:</span>
                    <span className="font-medium">{teammateSynergy.goalsPerGame}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Synergy Level:</span>
                    <span className={`font-bold ${
                      teammateSynergy.synergy.includes('High') ? 'text-green-600' : 
                      teammateSynergy.synergy.includes('Medium') ? 'text-yellow-600' : 
                      'text-red-600'
                    }`}>
                      {teammateSynergy.synergy}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center text-gray-500">
                <p>Select two different players and click Calculate Synergy to see results.</p>
              </div>
            )}
          </div>
        </div>
      </DashboardCard>
      
      {/* Head-to-Head Calculator */}
      <DashboardCard title="Head-to-Head Matchup Calculator">
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Player</label>
              <select 
                className="border border-gray-300 rounded-md py-2 px-4 w-full"
                value={selectedPlayer}
                onChange={(e) => setSelectedPlayer(e.target.value)}
              >
                {playerList.map(player => (
                  <option key={player} value={player}>{player}</option>
                ))}
              </select>
            </div>
            
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">Opponent</label>
              <select 
                className="border border-gray-300 rounded-md py-2 px-4 w-full"
                value={selectedOpponent}
                onChange={(e) => setSelectedOpponent(e.target.value)}
              >
                {playerList.map(player => (
                  <option key={player} value={player}>{player}</option>
                ))}
              </select>
            </div>
            
            <button 
              className="bg-primary-main text-white px-4 py-2 rounded-md hover:bg-primary-dark transition-colors"
              onClick={calculateOpponentMatchup}
            >
              Calculate Matchup
            </button>
          </div>
          
          <div className="bg-gray-50 p-6 rounded-lg">
            {playerMatchup ? (
              <div>
                <h3 className="text-lg font-semibold mb-4">Matchup Results</h3>
                {playerMatchup.estimated && (
                  <p className="text-sm text-yellow-600 mb-3">
                    No direct matchup data available. Results are estimated based on individual performance.
                  </p>
                )}
                <div className="space-y-3">
                  <div className="flex justify-between">
                    <span className="text-gray-600">Matchup:</span>
                    <span className="font-medium">{playerMatchup.player} vs {playerMatchup.opponent}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Games Played:</span>
                    <span className="font-medium">{playerMatchup.games}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Record:</span>
                    <span className="font-medium">{playerMatchup.wins}W - {playerMatchup.draws}D - {playerMatchup.losses}L</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Win Rate:</span>
                    <span className="font-medium">{playerMatchup.winRate}%</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-gray-600">Advantage:</span>
                    <span className={`font-bold ${
                      playerMatchup.wins > playerMatchup.losses ? 'text-green-600' : 
                      playerMatchup.wins < playerMatchup.losses ? 'text-red-600' : 
                      'text-yellow-600'
                    }`}>
                      {playerMatchup.wins > playerMatchup.losses
                        ? `${playerMatchup.player} has the advantage`
                        : playerMatchup.wins < playerMatchup.losses
                        ? `${playerMatchup.opponent} has the advantage`
                        : 'Even matchup'}
                    </span>
                  </div>
                </div>
              </div>
            ) : (
              <div className="text-center text-gray-500">
                <p>Select two different players and click Calculate Matchup to see results.</p>
              </div>
            )}
          </div>
        </div>
      </DashboardCard>
    </div>
  );
};

export default Performance; 