import React, { useState, useEffect } from 'react';
import axios from 'axios';
import { useHistory } from 'react-router-dom';
import './aiMapping.scss';
import './aiReview.scss';

interface Control {
  id: string;
  name: string;
  description: string;
  standard: string;
  section?: string;
}

interface CRE {
  id: string;
  external_id?: string;
  name: string;
  description: string;
  tags?: string[];
}

interface Mapping {
  control: Control;
  cre: CRE;
  confidence: number;
  reasoning?: string;
  requires_review: boolean;
  user_approved?: boolean;
}

interface Suggestion {
  name: string;
  description: string;
  tags: string[];
  potential_relationships: string[];
}

interface MappingResults {
  standard: string;
  mapped_controls: Mapping[];
  unmapped_controls: {
    control: Control;
    reason: string;
    attempted_cre?: CRE;
  }[];
  suggested_new_cres: Suggestion[];
  summary: {
    total_controls: number;
    mapped_count: number;
    unmapped_count: number;
    high_confidence_count: number;
    requires_review_count: number;
    processing_time?: string;
  };
}

export const AIReview: React.FC = () => {
  const [results, setResults] = useState<MappingResults | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedMappings, setSelectedMappings] = useState<{[key: number]: boolean}>({});
  const [selectedSuggestions, setSelectedSuggestions] = useState<{[key: number]: boolean}>({});
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);
  const [sortBy, setSortBy] = useState<string>('confidence');
  const [sortDirection, setSortDirection] = useState<'asc' | 'desc'>('desc');
  const [filterConfidence, setFilterConfidence] = useState<string>('all');
  const history = useHistory();

  useEffect(() => {
    const fetchResults = async () => {
      try {
        // Fetch the mapping results
        const response = await axios.get('/myopencre/ai-map/review-data');
        setResults(response.data);
        
        // Initialize selected mappings based on confidence
        if (response.data && response.data.mapped_controls) {
          const initialSelectedMappings = response.data.mapped_controls.reduce((acc: {[key: number]: boolean}, mapping: Mapping, index: number) => {
            acc[index] = mapping.confidence >= 0.8;
            return acc;
          }, {});
          setSelectedMappings(initialSelectedMappings);
        }
        
        setLoading(false);
      } catch (err) {
        setError('Failed to load mapping results. Please return to the mapping page and try again.');
        setLoading(false);
      }
    };

    fetchResults();
  }, []);

  const handleMappingToggle = (index: number) => {
    setSelectedMappings({
      ...selectedMappings,
      [index]: !selectedMappings[index]
    });
  };

  const handleSuggestionToggle = (index: number) => {
    setSelectedSuggestions({
      ...selectedSuggestions,
      [index]: !selectedSuggestions[index]
    });
  };
  
  const handleSelectAll = (select: boolean) => {
    if (!results?.mapped_controls) return;
    
    const newSelections: {[key: number]: boolean} = {};
    results.mapped_controls.forEach((_, index) => {
      newSelections[index] = select;
    });
    
    setSelectedMappings(newSelections);
  };
  
  const handleSelectByConfidence = (threshold: number, select: boolean) => {
    if (!results?.mapped_controls) return;
    
    const newSelections = {...selectedMappings};
    results.mapped_controls.forEach((mapping, index) => {
      if ((select && mapping.confidence >= threshold) || 
          (!select && mapping.confidence < threshold)) {
        newSelections[index] = true;
      } else {
        newSelections[index] = false;
      }
    });
    
    setSelectedMappings(newSelections);
  };
  
  const handleSort = (field: string) => {
    if (sortBy === field) {
      // Toggle direction if same field
      setSortDirection(sortDirection === 'asc' ? 'desc' : 'asc');
    } else {
      // Set new field and default to descending for confidence, ascending for others
      setSortBy(field);
      setSortDirection(field === 'confidence' ? 'desc' : 'asc');
    }
  };
  
  const handleFilterChange = (event: React.ChangeEvent<HTMLSelectElement>) => {
    setFilterConfidence(event.target.value);
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      // Create form data with selected mappings and suggestions
      const formData = new FormData();
      
      // Add selected mappings
      Object.entries(selectedMappings).forEach(([index, isSelected]) => {
        if (isSelected) {
          formData.append(`mapping_${index}`, '1');
        }
      });
      
      // Add selected suggestions
      Object.entries(selectedSuggestions).forEach(([index, isSelected]) => {
        if (isSelected) {
          formData.append(`suggestion_${index}`, '1');
        }
      });

      // Submit the form
      await axios.post('/myopencre/ai-map/confirm', formData);
      
      // Redirect to completion page
      history.push('/myopencre/ai-map/complete');
    } catch (err: any) {
      setError(err.response?.data?.error || 'An error occurred while saving mappings. Please try again.');
      setIsSubmitting(false);
    }
  };

  const getConfidenceClass = (confidence: number) => {
    if (confidence >= 0.8) return 'high-confidence';
    if (confidence >= 0.6) return 'medium-confidence';
    return 'low-confidence';
  };

  const getConfidenceText = (confidence: number) => {
    if (confidence >= 0.8) return 'High';
    if (confidence >= 0.6) return 'Medium';
    return 'Low';
  };

  const getConfidenceBadgeColor = (confidence: number) => {
    if (confidence >= 0.8) return 'success';
    if (confidence >= 0.6) return 'warning';
    return 'danger';
  };
  
  const getSelectedCount = () => {
    return Object.values(selectedMappings).filter(Boolean).length;
  };
  
  // Sort and filter mappings
  const getSortedAndFilteredMappings = () => {
    if (!results?.mapped_controls) return [];
    
    // First apply filtering
    let filtered = [...results.mapped_controls];
    if (filterConfidence !== 'all') {
      const threshold = parseFloat(filterConfidence);
      filtered = filtered.filter(mapping => {
        if (filterConfidence === '0.8') {
          return mapping.confidence >= threshold;
        } else if (filterConfidence === '0.6') {
          return mapping.confidence >= 0.6 && mapping.confidence < 0.8;
        } else {
          return mapping.confidence < 0.6;
        }
      });
    }
    
    // Then apply sorting
    return filtered.sort((a, b) => {
      if (sortBy === 'confidence') {
        return sortDirection === 'asc' 
          ? a.confidence - b.confidence 
          : b.confidence - a.confidence;
      } else if (sortBy === 'control') {
        const aName = a.control.name || '';
        const bName = b.control.name || '';
        return sortDirection === 'asc'
          ? aName.localeCompare(bName)
          : bName.localeCompare(aName);
      } else if (sortBy === 'cre') {
        const aName = a.cre.name || '';
        const bName = b.cre.name || '';
        return sortDirection === 'asc'
          ? aName.localeCompare(bName)
          : bName.localeCompare(aName);
      }
      return 0;
    });
  };

  if (loading) {
    return (
      <div className="ai-review-loading">
        <div className="loading-spinner"></div>
        <p>Loading mapping results...</p>
      </div>
    );
  }

  if (!results) {
    return (
      <div className="ai-review-error">
        <h2>No mapping results found</h2>
        <p>Please return to the mapping page and try again.</p>
        <button onClick={() => history.push('/myopencre/ai-map')}>
          Return to Mapping
        </button>
      </div>
    );
  }

  const sortedMappings = getSortedAndFilteredMappings();
  
  return (
    <div className="ai-review-container">
      <div className="ai-review-header">
        <h1>Review AI-Generated Mappings</h1>
        <p>
          Standard: <strong>{results.standard}</strong>
        </p>
        <p className="ai-review-summary">
          {results.summary.mapped_count} mapped controls, 
          {results.summary.unmapped_count} unmapped controls
        </p>
        {results.summary.processing_time && (
          <p className="ai-review-timing">
            Processing time: {results.summary.processing_time}s
          </p>
        )}
      </div>

      {error && <div className="ai-review-error">{error}</div>}

      {/* Summary Card */}
      <div className="ai-review-summary-card">
        <div className="ai-review-summary-item">
          <h3 className="text-success">{results.summary.high_confidence_count}</h3>
          <p>High Confidence</p>
        </div>
        <div className="ai-review-summary-item">
          <h3 className="text-warning">{results.summary.requires_review_count}</h3>
          <p>Needs Review</p>
        </div>
        <div className="ai-review-summary-item">
          <h3 className="text-danger">{results.summary.unmapped_count}</h3>
          <p>Unmapped</p>
        </div>
        <div className="ai-review-summary-item">
          <h3 className="text-info">{results.suggested_new_cres.length}</h3>
          <p>Suggested CREs</p>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="ai-review-form">
        {/* Mapped Controls Section */}
        <div className="ai-review-toolbar">
          <h2>Mapped Controls <span className="ai-review-selection-count">({getSelectedCount()} selected)</span></h2>
          
          <div className="ai-review-actions-bar">
            <div className="ai-review-bulk-actions">
              <button 
                type="button" 
                className="ai-review-action-button"
                onClick={() => handleSelectAll(true)}
              >
                Select All
              </button>
              <button 
                type="button" 
                className="ai-review-action-button"
                onClick={() => handleSelectAll(false)}
              >
                Clear All
              </button>
              <button 
                type="button" 
                className="ai-review-action-button"
                onClick={() => handleSelectByConfidence(0.8, true)}
              >
                Select High Confidence
              </button>
            </div>
            
            <div className="ai-review-filter-sort">
              <div className="ai-review-filter">
                <label htmlFor="confidenceFilter">Filter: </label>
                <select 
                  id="confidenceFilter" 
                  value={filterConfidence} 
                  onChange={handleFilterChange}
                >
                  <option value="all">All Confidence Levels</option>
                  <option value="0.8">High Confidence Only</option>
                  <option value="0.6">Medium Confidence Only</option>
                  <option value="0.0">Low Confidence Only</option>
                </select>
              </div>
              
              <div className="ai-review-sort">
                <button 
                  type="button"
                  className={`ai-review-sort-button ${sortBy === 'confidence' ? 'active' : ''}`}
                  onClick={() => handleSort('confidence')}
                >
                  Confidence {sortBy === 'confidence' && (sortDirection === 'asc' ? '↑' : '↓')}
                </button>
                <button 
                  type="button"
                  className={`ai-review-sort-button ${sortBy === 'control' ? 'active' : ''}`}
                  onClick={() => handleSort('control')}
                >
                  Control {sortBy === 'control' && (sortDirection === 'asc' ? '↑' : '↓')}
                </button>
                <button 
                  type="button"
                  className={`ai-review-sort-button ${sortBy === 'cre' ? 'active' : ''}`}
                  onClick={() => handleSort('cre')}
                >
                  CRE {sortBy === 'cre' && (sortDirection === 'asc' ? '↑' : '↓')}
                </button>
              </div>
            </div>
          </div>
        </div>

        {results.mapped_controls.length > 0 ? (
          <div className="ai-review-mappings">
            {sortedMappings.map((mapping, index) => (
              <div 
                key={`mapping-${index}`} 
                className={`ai-review-mapping ${getConfidenceClass(mapping.confidence)}`}
              >
                <div className="ai-review-mapping-content">
                  <div className="ai-review-control">
                    <h4>{mapping.control.name}</h4>
                    <p className="ai-review-id">{mapping.control.id}</p>
                    <p className="ai-review-description">{mapping.control.description}</p>
                  </div>
                  
                  <div className="ai-review-arrow">
                    <i className="fas fa-arrow-right"></i>
                  </div>
                  
                  <div className="ai-review-cre">
                    <div className="ai-review-cre-header">
                      <h4>{mapping.cre.name}</h4>
                      <span className={`ai-review-confidence-badge ${getConfidenceBadgeColor(mapping.confidence)}`}>
                        {getConfidenceText(mapping.confidence)} ({mapping.confidence.toFixed(2)})
                      </span>
                    </div>
                    <p className="ai-review-id">{mapping.cre.id || mapping.cre.external_id}</p>
                    <p className="ai-review-description">{mapping.cre.description}</p>
                    
                    <div className="ai-review-approval">
                      <label className="ai-review-checkbox">
                        <input
                          type="checkbox"
                          checked={selectedMappings[index] || false}
                          onChange={() => handleMappingToggle(index)}
                          disabled={isSubmitting}
                        />
                        Approve this mapping
                      </label>
                    </div>
                  </div>
                </div>
                
                {mapping.reasoning && (
                  <div className="ai-review-reasoning">
                    <strong>AI Reasoning:</strong> {mapping.reasoning}
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="ai-review-empty">No mappings were found for this standard.</div>
        )}

        {/* Suggested New CREs Section */}
        {results.suggested_new_cres.length > 0 && (
          <>
            <div className="ai-review-section-divider">Suggested New CREs</div>
            
            <h2>Suggested New CREs</h2>
            <p className="ai-review-subheading">
              The AI suggests creating the following new CREs for controls that couldn't be mapped.
              Select which suggestions you want to save.
            </p>

            <div className="ai-review-suggestions">
              {results.suggested_new_cres.map((suggestion, index) => (
                <div key={`suggestion-${index}`} className="ai-review-suggestion">
                  <div className="ai-review-suggestion-header">
                    <h4>{suggestion.name}</h4>
                    <label className="ai-review-checkbox">
                      <input
                        type="checkbox"
                        checked={selectedSuggestions[index] || false}
                        onChange={() => handleSuggestionToggle(index)}
                        disabled={isSubmitting}
                      />
                      Save this suggestion
                    </label>
                  </div>
                  
                  <p className="ai-review-description">{suggestion.description}</p>
                  
                  {suggestion.tags && suggestion.tags.length > 0 && (
                    <div className="ai-review-tags">
                      {suggestion.tags.map((tag, tagIndex) => (
                        <span key={`tag-${index}-${tagIndex}`} className="ai-review-tag">
                          {tag}
                        </span>
                      ))}
                    </div>
                  )}
                  
                  {suggestion.potential_relationships && suggestion.potential_relationships.length > 0 && (
                    <div className="ai-review-relationships">
                      <h5>Potential Relationships:</h5>
                      <ul>
                        {suggestion.potential_relationships.map((rel, relIndex) => (
                          <li key={`rel-${index}-${relIndex}`}>{rel}</li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              ))}
            </div>
          </>
        )}

        <div className="ai-review-actions">
          <button 
            type="button" 
            className="ai-review-button secondary"
            onClick={() => history.push('/myopencre/ai-map')}
            disabled={isSubmitting}
          >
            Back
          </button>
          <button 
            type="submit" 
            className="ai-review-button primary"
            disabled={isSubmitting}
          >
            {isSubmitting ? 'Saving...' : 'Save Approved Mappings'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default AIReview; 