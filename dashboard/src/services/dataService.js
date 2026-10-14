import * as XLSX from 'xlsx';
import _ from 'lodash';

// Mock data for development
const mockData = {
  players: [
    { id: 1, name: 'Canova', games: 8, wins: 7, draws: 0, losses: 1, goalsFor: 64, goalsAgainst: 37, goalDiff: 27, points: 21 },
    { id: 2, name: 'Rodrigo', games: 7, wins: 5, draws: 1, losses: 1, goalsFor: 48, goalsAgainst: 32, goalDiff: 16, points: 16 },
    { id: 3, name: 'Felipe', games: 6, wins: 4, draws: 0, losses: 2, goalsFor: 42, goalsAgainst: 28, goalDiff: 14, points: 12 },
    { id: 4, name: 'Lucas', games: 8, wins: 3, draws: 2, losses: 3, goalsFor: 38, goalsAgainst: 40, goalDiff: -2, points: 11 },
    { id: 5, name: 'Bruno', games: 7, wins: 3, draws: 1, losses: 3, goalsFor: 35, goalsAgainst: 36, goalDiff: -1, points: 10 },
  ],
  tournaments: [
    { id: '251', name: 'Tournament 251', type: 'table' },
    { id: '250', name: 'Tournament 250', type: 'table' },
    { id: '249', name: 'Tournament 249', type: 'table' },
    { id: 'COPA_2023', name: 'Copa BioFut 2023', type: 'cup' },
  ],
  confrontos: [
    { player1: 'Canova', player2: 'Rodrigo', games: 5, wins: 3, draws: 1, losses: 1 },
    { player1: 'Canova', player2: 'Felipe', games: 4, wins: 3, draws: 0, losses: 1 },
    { player1: 'Rodrigo', player2: 'Felipe', games: 6, wins: 4, draws: 0, losses: 2 },
  ]
};

// Process data to extract players and stats
const processDataStructure = (data) => {
  if (!data) return data;
  
  // Extract players from historical data
  const processedData = { ...data };
  
  // Use a Map to store players by name for de-duplication
  const playersMap = new Map();
  
  // Process historical data
  if (processedData.historical && Array.isArray(processedData.historical)) {
    processedData.historical.forEach(player => {
      if (!player.name) return;
      
      // Initialize the player in the map if not exists
      if (!playersMap.has(player.name)) {
        playersMap.set(player.name, {
          name: player.name,
          games: player.games || 0,
          wins: player.victories || 0,
          draws: player.draws || 0,
          losses: player.defeats || 0,
          points: player.points || 0,
          goalsFor: 0,
          goalsAgainst: 0,
          goalDiff: 0,
          winRate: player.games > 0 ? Math.round((player.victories / player.games) * 100) : 0,
          effectiveness: player.games > 0 ? Math.round(((player.points / (player.games * 3)) * 100)) : 0
        });
      } else {
        // Update existing player with additional data
        const existingPlayer = playersMap.get(player.name);
        existingPlayer.games += player.games || 0;
        existingPlayer.wins += player.victories || 0;
        existingPlayer.draws += player.draws || 0;
        existingPlayer.losses += player.defeats || 0;
        existingPlayer.points += player.points || 0;
        
        // Recalculate derived stats
        if (existingPlayer.games > 0) {
          existingPlayer.winRate = Math.round((existingPlayer.wins / existingPlayer.games) * 100);
          existingPlayer.effectiveness = Math.round(((existingPlayer.points / (existingPlayer.games * 3)) * 100));
        }
      }
    });
  }
  
  // Process tournament data - uses JOGADOR instead of name
  if (processedData.tournaments && typeof processedData.tournaments === 'object') {
    Object.keys(processedData.tournaments).forEach(tournamentId => {
      const tournamentData = processedData.tournaments[tournamentId];
      if (Array.isArray(tournamentData)) {
        tournamentData.forEach(entry => {
          // Use JOGADOR field for player name in tournament data
          const playerName = entry.JOGADOR;
          if (!playerName) return; // Skip entries without player name
          
          // Initialize or update player stats
          if (!playersMap.has(playerName)) {
            playersMap.set(playerName, {
              name: playerName,
              games: entry.J || 0,
              wins: entry.V || 0,
              draws: entry.E || 0,
              losses: entry.D || 0,
              points: entry.PONTOS || 0,
              goalsFor: entry.Gfeitos || 0,
              goalsAgainst: entry.Gsofr || 0,
              goalDiff: entry.SG || 0,
              assists: entry.Assists || 0,
              winRate: 0,
              effectiveness: 0
            });
          } else {
            // Update existing player with tournament data
            const player = playersMap.get(playerName);
            player.games += entry.J || 0;
            player.wins += entry.V || 0;
            player.draws += entry.E || 0;
            player.losses += entry.D || 0;
            player.points += entry.PONTOS || 0;
            player.goalsFor = (player.goalsFor || 0) + (entry.Gfeitos || 0);
            player.goalsAgainst = (player.goalsAgainst || 0) + (entry.Gsofr || 0);
            player.goalDiff = (player.goalDiff || 0) + (entry.SG || 0);
            player.assists = (player.assists || 0) + (entry.Assists || 0);
          }
          
          // Calculate derived stats
          const player = playersMap.get(playerName);
          if (player.games > 0) {
            player.winRate = Math.round((player.wins / player.games) * 100);
            player.effectiveness = Math.round(((player.points / (player.games * 3)) * 100));
            player.goalsPerGame = +(player.goalsFor / player.games).toFixed(2);
          }
        });
      }
    });
  }
  
  // Update player stats with goal information from database
  if (processedData.database && Array.isArray(processedData.database)) {
    processedData.database.forEach(entry => {
      if (entry.Nome) {
        // Get or create the player in the map
        if (!playersMap.has(entry.Nome)) {
          playersMap.set(entry.Nome, {
            name: entry.Nome,
            games: 0,
            wins: 0, 
            draws: 0,
            losses: 0,
            points: 0,
            goalsFor: 0,
            goalsAgainst: 0,
            goalDiff: 0
          });
        }
        
        // Update the player stats
        const player = playersMap.get(entry.Nome);
        player.goalsFor = (player.goalsFor || 0) + (entry['Gols a Favor'] || 0);
        player.goalsAgainst = (player.goalsAgainst || 0) + (entry['Gols Contra'] || 0);
        player.goalDiff = player.goalsFor - player.goalsAgainst;
        player.goalsPerGame = player.games > 0 ? +(player.goalsFor / player.games).toFixed(2) : 0;
        player.assists = (player.assists || 0) + (entry['Assistência'] || 0);
      }
    });
  }
  
  // Convert the player map back to an array
  processedData.players = Array.from(playersMap.values());
  
  return processedData;
};

// Load data from JSON file
const loadExcelData = async () => {
  try {
    // Use the correct path to the JSON file
    const response = await fetch('/biofut_data/biofut_data.json');
    if (!response.ok) {
      throw new Error(`Failed to fetch data: ${response.status} ${response.statusText}`);
    }
    
    const data = await response.json();
    console.log('Successfully loaded BioFut data');
    
    // Process the data structure to extract players, teams, etc.
    const processedData = processDataStructure(data);
    
    // Cache the data for other functions to use
    window.__biofutData = processedData;
    
    return processedData;
  } catch (error) {
    console.error('Error loading BioFut data:', error);
    // Fallback to mock data in case of error
    console.warn('Falling back to mock data');
    window.__biofutData = mockData;
    return mockData;
  }
};

// Process player statistics
const getPlayerStats = (playerName, tournaments = []) => {
  // Use the cached data if available
  const data = window.__biofutData || {};
  
  // If no tournaments are selected, use all tournaments
  const filteredData = tournaments && tournaments.length > 0
    ? filterDataByTournaments(data, tournaments)
    : data;
  
  // First try to find the player in the filtered data
  const playerStats = filteredData.players?.find(p => p.name === playerName);
  
  if (playerStats) {
    return playerStats;
  }
  
  // If player not found in filtered data, try to find the player in the original data
  // This is a fallback to ensure we always return some player data
  const originalPlayerStats = data.players?.find(p => p.name === playerName);
  
  if (originalPlayerStats) {
    console.warn(`Player ${playerName} not found in filtered data, using original data`);
    return originalPlayerStats;
  }
  
  // Create a placeholder player if not found anywhere
  console.warn(`Player ${playerName} not found in data`);
  return {
    name: playerName,
    games: 0,
    wins: 0,
    draws: 0,
    losses: 0,
    points: 0,
    goalsFor: 0,
    goalsAgainst: 0,
    goalDiff: 0,
    winRate: 0,
    effectiveness: 0
  };
};

// New function to filter data by tournaments
const filterDataByTournaments = (data, tournamentIds) => {
  if (!data || !tournamentIds || tournamentIds.length === 0) {
    return data;
  }
  
  // Create a new filtered data object
  const filteredData = { ...data };
  
  // Important: DON'T filter out the players array as it contains the master list of players
  if (!filteredData.players && data.players) {
    filteredData.players = [...data.players];
  }
  
  // Create a new Map to aggregate player stats based on selected tournaments
  const aggregatedPlayerStats = new Map();
  
  // Initialize the player map with all existing players to maintain the full player list
  if (filteredData.players) {
    filteredData.players.forEach(player => {
      aggregatedPlayerStats.set(player.name, {
        ...player,
        // Reset the stats that will be aggregated from selected tournaments
        games: 0,
        wins: 0,
        draws: 0,
        losses: 0,
        points: 0,
        goalsFor: 0,
        goalsAgainst: 0,
        goalDiff: 0
      });
    });
  }
  
  // Process selected tournament data
  if (filteredData.tournaments) {
    Object.keys(filteredData.tournaments).forEach(tournamentId => {
      // Only process selected tournaments
      if (tournamentIds.includes(tournamentId)) {
        const tournamentData = filteredData.tournaments[tournamentId];
        if (Array.isArray(tournamentData)) {
          tournamentData.forEach(entry => {
            // Use JOGADOR field instead of name (as shown in the data analysis)
            const playerName = entry.JOGADOR || entry.name;
            if (playerName) {
              // Get or create player in the aggregated stats map
              if (!aggregatedPlayerStats.has(playerName)) {
                aggregatedPlayerStats.set(playerName, {
                  name: playerName,
                  games: 0,
                  wins: 0,
                  draws: 0,
                  losses: 0,
                  points: 0,
                  goalsFor: 0,
                  goalsAgainst: 0,
                  goalDiff: 0
                });
              }
              
              // Update player stats with this tournament's data
              const playerStats = aggregatedPlayerStats.get(playerName);
              // Use appropriate field mappings based on tournament data schema
              playerStats.games += entry.J || 0;  // J = games
              playerStats.wins += entry.V || 0;   // V = victories
              playerStats.draws += entry.E || 0;  // E = draws
              playerStats.losses += entry.D || 0; // D = losses
              playerStats.points += entry.PONTOS || 0; // PONTOS = points
              playerStats.goalsFor += entry.Gfeitos || 0; // Gfeitos = goals scored
              playerStats.goalsAgainst += entry.Gsofr || 0; // Gsofr = goals against
              playerStats.goalDiff += entry.SG || 0; // SG = goal difference
              playerStats.assists += entry.Assists || 0; // Assists
              
              // Calculate derived stats
              if (playerStats.games > 0) {
                playerStats.winRate = Math.round((playerStats.wins / playerStats.games) * 100);
                playerStats.effectiveness = Math.round(((playerStats.points / (playerStats.games * 3)) * 100));
                playerStats.goalsPerGame = +(playerStats.goalsFor / playerStats.games).toFixed(2);
              }
            }
          });
        }
      }
    });
  }
  
  // Add database stats if database is selected
  if (tournamentIds.includes('database') && filteredData.database) {
    filteredData.database.forEach(entry => {
      if (entry.Nome) {
        // Get or create player in the aggregated stats map
        if (!aggregatedPlayerStats.has(entry.Nome)) {
          aggregatedPlayerStats.set(entry.Nome, {
            name: entry.Nome,
            games: 0,
            wins: 0, 
            draws: 0,
            losses: 0,
            points: 0,
            goalsFor: 0,
            goalsAgainst: 0,
            goalDiff: 0
          });
        }
        
        // Update player stats with database data
        const playerStats = aggregatedPlayerStats.get(entry.Nome);
        playerStats.goalsFor = (playerStats.goalsFor || 0) + (entry['Gols a Favor'] || 0);
        playerStats.goalsAgainst = (playerStats.goalsAgainst || 0) + (entry['Gols Contra'] || 0);
        playerStats.goalDiff = playerStats.goalsFor - playerStats.goalsAgainst;
        playerStats.goalsPerGame = playerStats.games > 0 ? +(playerStats.goalsFor / playerStats.games).toFixed(2) : 0;
        playerStats.assists = (playerStats.assists || 0) + (entry['Assistência'] || 0);
      }
    });
  }
  
  // Add historical stats if historical is selected
  if (tournamentIds.includes('historical') && filteredData.historical) {
    filteredData.historical.forEach(entry => {
      if (entry.name) {
        // Get or create player in the aggregated stats map
        if (!aggregatedPlayerStats.has(entry.name)) {
          aggregatedPlayerStats.set(entry.name, {
            name: entry.name,
            games: 0,
            wins: 0,
            draws: 0,
            losses: 0,
            points: 0,
            goalsFor: 0,
            goalsAgainst: 0,
            goalDiff: 0
          });
        }
        
        // Update player stats with historical data
        const playerStats = aggregatedPlayerStats.get(entry.name);
        playerStats.games += entry.games || 0;
        playerStats.wins += entry.victories || 0;
        playerStats.draws += entry.draws || 0;
        playerStats.losses += entry.defeats || 0;
        playerStats.points += entry.points || 0;
        
        // Calculate derived stats
        if (playerStats.games > 0) {
          playerStats.winRate = Math.round((playerStats.wins / playerStats.games) * 100);
          playerStats.effectiveness = Math.round(((playerStats.points / (playerStats.games * 3)) * 100));
        }
      }
    });
  }
  
  // Update the players array with the aggregated stats
  filteredData.players = Array.from(aggregatedPlayerStats.values());
  
  return filteredData;
};

// Get top players by criteria
const getTopPlayers = (criteria, limit = 5, tournaments = []) => {
  // Use the cached data if available
  const data = window.__biofutData || {};
  
  // If no tournaments are selected, use all tournaments
  const filteredData = tournaments && tournaments.length > 0
    ? filterDataByTournaments(data, tournaments)
    : data;
  
  // Get sorted players based on criteria
  const players = filteredData.players || [];
  
  if (players.length === 0) {
    return [];
  }
  
  // Map players to the format needed for charts
  const mappedPlayers = players.map(player => {
    let value = 0;
    
    if (criteria === 'points') {
      value = player.points || 0;
    } else if (criteria === 'wins') {
      value = player.wins || 0;
    } else if (criteria === 'goals') {
      value = player.goalsFor || 0;
    } else if (criteria === 'goalDiff') {
      value = player.goalDiff || 0;
    } else if (criteria === 'assists') {
      value = player.assists || 0;
    }
    
    return {
      name: player.name,
      value
    };
  });
  
  // Sort by the requested criteria (value)
  const sortedPlayers = [...mappedPlayers].sort((a, b) => b.value - a.value);
  
  return sortedPlayers.slice(0, limit);
};

// Get head-to-head matchup data
const getOpponentMatchup = (player, opponent) => {
  // Use the cached data
  const data = window.__biofutData || {};
  
  // Find direct confronto
  const confronto = data.confrontos?.find(c => 
    (c.player1 === player && c.player2 === opponent) || 
    (c.player1 === opponent && c.player2 === player)
  );
  
  if (!confronto) {
    return {
      player,
      opponent,
      gamesPlayed: 0,
      wins: 0,
      draws: 0,
      losses: 0,
      winRate: '0.0'
    };
  }
  
  // Normalize the data to ensure player is player1
  const isPlayer1 = confronto.player1 === player;
  const gamesPlayed = confronto.games;
  
  return {
    player,
    opponent,
    gamesPlayed,
    wins: isPlayer1 ? confronto.wins : confronto.losses,
    draws: confronto.draws,
    losses: isPlayer1 ? confronto.losses : confronto.wins,
    winRate: ((isPlayer1 ? confronto.wins : confronto.losses) / gamesPlayed * 100).toFixed(1)
  };
};

// Save loaded data to window for easy access
// This is a simple caching mechanism
window.__biofutData = null;

// Hook to get our loaded data once
const getLoadedData = async () => {
  // Only load the data once - return the cached data if it exists
  if (window.__biofutData) {
    return window.__biofutData;
  }
  
  // Load the data and cache it
  try {
    const data = await loadExcelData();
    window.__biofutData = data;
    return data;
  } catch (error) {
    console.error('Error in getLoadedData:', error);
    return null;
  }
};

export {
  loadExcelData,
  getPlayerStats,
  getTopPlayers,
  getOpponentMatchup,
  getLoadedData,
  processDataStructure
}; 