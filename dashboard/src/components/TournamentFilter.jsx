import React from 'react';

const TournamentFilter = ({ 
  tournaments = {}, 
  selectedTournaments = [], 
  onTournamentSelect, 
  onSelectAll 
}) => {
  // Handle the data structure correctly
  const tournamentsArray = [];
  
  if (tournaments) {
    // Only add real tournament IDs from the tournaments object if it exists
    if (tournaments.tournaments && typeof tournaments.tournaments === 'object') {
      Object.keys(tournaments.tournaments).forEach(id => {
        const tournamentData = tournaments.tournaments[id];
        if (Array.isArray(tournamentData) && tournamentData.length > 0) {
          tournamentsArray.push({
            id,
            name: `Tournament ${id} (${tournamentData.length} entries)`
          });
        }
      });
    }
  }
  
  const allSelected = tournamentsArray.length > 0 && selectedTournaments.length === tournamentsArray.length;
  
  return (
    <div className="bg-white rounded-lg shadow p-4 mb-6">
      <div className="flex items-center mb-3">
        <h3 className="text-lg font-semibold">Filter by Tournaments</h3>
        <div className="ml-auto">
          <label className="inline-flex items-center">
            <input
              type="checkbox"
              className="form-checkbox h-5 w-5 text-blue-600 rounded"
              checked={allSelected}
              onChange={() => onSelectAll(!allSelected)}
            />
            <span className="ml-2">Select All</span>
          </label>
        </div>
      </div>
      
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-2">
        {tournamentsArray.map(tournament => (
          <label key={tournament.id} className="inline-flex items-center">
            <input
              type="checkbox"
              className="form-checkbox h-5 w-5 text-blue-600 rounded"
              checked={selectedTournaments.includes(tournament.id)}
              onChange={(e) => onTournamentSelect(tournament.id, e.target.checked)}
            />
            <span className="ml-2 truncate">{tournament.name}</span>
          </label>
        ))}
      </div>
    </div>
  );
};

export default TournamentFilter; 