import { useState, useEffect, useMemo } from 'react';
import { loadExcelData } from '../services/dataService';

const useDataLoader = () => {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedTournaments, setSelectedTournaments] = useState([]);
  
  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const result = await loadExcelData();
        setData(result);
        
        // Get available dataset ids
        const availableDatasets = [];
        
        // Include both database and historical for complete player data
        if (result.database && Array.isArray(result.database) && result.database.length > 0) {
          availableDatasets.push('database');
        }
        
        if (result.historical && Array.isArray(result.historical) && result.historical.length > 0) {
          availableDatasets.push('historical');
        }
        
        // Add real tournament IDs
        if (result.tournaments && typeof result.tournaments === 'object') {
          Object.keys(result.tournaments)
            .filter(key => Array.isArray(result.tournaments[key]) && result.tournaments[key].length > 0)
            .forEach(id => availableDatasets.push(id));
        }
        
        // Set default to all available datasets
        if (availableDatasets.length > 0) {
          setSelectedTournaments(availableDatasets);
        }
        
        setLoading(false);
      } catch (err) {
        console.error("Error loading data:", err);
        setError(err.message);
        setLoading(false);
      }
    };
    
    fetchData();
  }, []);
  
  // Filter data based on selected tournaments
  const filteredData = useMemo(() => {
    if (!data || selectedTournaments.length === 0) return data;
    
    // Create a shallow copy of the data object
    const filtered = { ...data };
    
    // Create new arrays for database and historical to avoid mutating the original
    filtered.database = [...(data.database || [])];
    filtered.historical = [...(data.historical || [])];
    
    // If database is not selected, empty the array but keep the property
    if (!selectedTournaments.includes('database')) {
      filtered.database = [];
    }
    
    // If historical is not selected, empty the array but keep the property
    if (!selectedTournaments.includes('historical')) {
      filtered.historical = [];
    }
    
    // Create a shallow copy of the tournaments object
    if (data.tournaments) {
      filtered.tournaments = { ...data.tournaments };
      
      // For each tournament in the original data
      Object.keys(data.tournaments).forEach(id => {
        // If this tournament is not selected, replace with empty array
        if (!selectedTournaments.includes(id)) {
          filtered.tournaments[id] = [];
        } else {
          // Otherwise, copy the array
          filtered.tournaments[id] = [...data.tournaments[id]];
        }
      });
    }
    
    return filtered;
  }, [data, selectedTournaments]);
  
  const handleTournamentSelection = (tournamentId, isSelected) => {
    if (isSelected) {
      setSelectedTournaments(prev => [...prev, tournamentId]);
    } else {
      setSelectedTournaments(prev => prev.filter(id => id !== tournamentId));
    }
  };
  
  const handleSelectAllTournaments = (selectAll) => {
    if (selectAll && data) {
      const availableDatasets = [];
      
      // Include both database and historical for complete player data
      if (data.database && Array.isArray(data.database) && data.database.length > 0) {
        availableDatasets.push('database');
      }
      
      if (data.historical && Array.isArray(data.historical) && data.historical.length > 0) {
        availableDatasets.push('historical');
      }
      
      // Add real tournament IDs
      if (data.tournaments && typeof data.tournaments === 'object') {
        Object.keys(data.tournaments)
          .filter(key => Array.isArray(data.tournaments[key]) && data.tournaments[key].length > 0)
          .forEach(id => availableDatasets.push(id));
      }
      
      setSelectedTournaments(availableDatasets);
    } else {
      setSelectedTournaments([]);
    }
  };
  
  return {
    data: filteredData, // Return filtered data instead of raw data
    rawData: data,      // Also provide access to unfiltered data if needed
    loading,
    error,
    selectedTournaments,
    handleTournamentSelection,
    handleSelectAllTournaments
  };
};

export default useDataLoader; 