import React, { useState, useEffect } from 'react';
import axios from 'axios';
import './aiMapping.scss';

export const AIMapping: React.FC = () => {
  const [standards, setStandards] = useState<string[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [selectedStandard, setSelectedStandard] = useState<string>('');
  const [file, setFile] = useState<File | null>(null);
  const [standardType, setStandardType] = useState<string>('');
  const [confidenceThreshold, setConfidenceThreshold] = useState<number>(0.75);
  const [useLLM, setUseLLM] = useState<boolean>(true);
  const [generateSuggestions, setGenerateSuggestions] = useState<boolean>(true);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Fetch available standards
  useEffect(() => {
    const fetchStandards = async () => {
      try {
        const response = await axios.get('/api/standards');
        setStandards(response.data);
        setLoading(false);
      } catch (err) {
        setError('Failed to load standards. Please try again later.');
        setLoading(false);
      }
    };

    fetchStandards();
  }, []);

  const handleStandardChange = (e: React.ChangeEvent<HTMLSelectElement>) => {
    setSelectedStandard(e.target.value);
    if (e.target.value) {
      setFile(null);
    }
  };

  const handleFileChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      setFile(e.target.files[0]);
      setSelectedStandard('');
    } else {
      setFile(null);
    }
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSubmitting(true);
    setError(null);

    try {
      const formData = new FormData();
      
      if (selectedStandard) {
        formData.append('standard', selectedStandard);
      } 
      
      if (file) {
        formData.append('standard_file', file);
        formData.append('standard_type', standardType);
      }

      formData.append('confidence_threshold', confidenceThreshold.toString());
      formData.append('use_llm', useLLM ? '1' : '0');
      formData.append('generate_suggestions', generateSuggestions ? '1' : '0');

      await axios.post('/myopencre/ai-map/process', formData, {
        headers: {
          'Content-Type': 'multipart/form-data'
        }
      });

      // Redirect to review page
      window.location.href = '/myopencre/ai-map/review';
    } catch (err: any) {
      setError(err.response?.data?.error || 'An error occurred during processing. Please try again.');
      setIsSubmitting(false);
    }
  };

  if (loading) {
    return (
      <div className="ai-mapping-loading">
        <div className="loading-spinner"></div>
        <p>Loading standards...</p>
      </div>
    );
  }

  if (isSubmitting) {
    return (
      <div className="ai-mapping-loading">
        <div className="loading-spinner"></div>
        <p>Processing your standard with AI. This may take several minutes...</p>
        <p className="loading-note">Please don't close or refresh this page.</p>
      </div>
    );
  }

  return (
    <div className="ai-mapping-container">
      <div className="ai-mapping-header">
        <h1>AI-Powered Standard Mapping</h1>
        <p>Map compliance standards to CREs automatically using AI technology.</p>
      </div>

      {error && <div className="ai-mapping-error">{error}</div>}

      <form onSubmit={handleSubmit} className="ai-mapping-form">
        <div className="ai-mapping-options">
          <div className="ai-mapping-option">
            <h3>Option 1: Select Existing Standard</h3>
            <div className="form-group">
              <label htmlFor="standard">Standard</label>
              <select 
                id="standard" 
                value={selectedStandard} 
                onChange={handleStandardChange}
                disabled={!!file || isSubmitting}
              >
                <option value="">-- Select a standard --</option>
                {standards.map(standard => (
                  <option key={standard} value={standard}>
                    {standard}
                  </option>
                ))}
              </select>
            </div>
          </div>

          <div className="ai-mapping-option">
            <h3>Option 2: Upload Standard File</h3>
            <div className="form-group">
              <label htmlFor="standard_file">Standard File (CSV, JSON, TXT)</label>
              <input 
                type="file" 
                id="standard_file"
                onChange={handleFileChange}
                disabled={!!selectedStandard || isSubmitting}
              />
              <small className="help-text">
                Upload a file containing standard controls.
                Supported formats: CSV, JSON, TXT
              </small>
            </div>

            <div className="form-group">
              <label htmlFor="standard_type">Standard Type</label>
              <select 
                id="standard_type"
                value={standardType}
                onChange={(e) => setStandardType(e.target.value)}
                disabled={!file || isSubmitting}
              >
                <option value="">Auto-detect</option>
                <option value="pci_dss">PCI DSS</option>
                <option value="soc2">SOC 2</option>
                <option value="dora">DORA</option>
                <option value="owasp_ai">OWASP AI/LLM</option>
                <option value="generic">Generic Standard</option>
              </select>
            </div>
          </div>
        </div>

        <div className="ai-mapping-settings">
          <h3>AI Mapping Settings</h3>
          
          <div className="form-group">
            <label htmlFor="confidence_threshold">Confidence Threshold: {confidenceThreshold}</label>
            <input 
              type="range" 
              id="confidence_threshold"
              min="0.5" 
              max="0.95" 
              step="0.05"
              value={confidenceThreshold}
              onChange={(e) => setConfidenceThreshold(parseFloat(e.target.value))}
              disabled={isSubmitting}
            />
            <div className="threshold-range">
              <span>More mappings (0.5)</span>
              <span>Higher precision (0.95)</span>
            </div>
          </div>
          
          <div className="form-check">
            <input 
              type="checkbox" 
              id="use_llm" 
              checked={useLLM}
              onChange={(e) => setUseLLM(e.target.checked)}
              disabled={isSubmitting}
            />
            <label htmlFor="use_llm">
              Use LLM for verification (higher quality but slower)
            </label>
          </div>
          
          <div className="form-check">
            <input 
              type="checkbox" 
              id="generate_suggestions" 
              checked={generateSuggestions}
              onChange={(e) => setGenerateSuggestions(e.target.checked)}
              disabled={isSubmitting}
            />
            <label htmlFor="generate_suggestions">
              Generate suggestions for unmapped controls
            </label>
          </div>
        </div>

        <div className="ai-mapping-info">
          <p>
            <span className="info-icon">ℹ</span>
            This process may take several minutes depending on the size of the standard.
          </p>
        </div>

        <div className="ai-mapping-submit">
          <button type="submit" disabled={(!selectedStandard && !file) || isSubmitting}>
            {isSubmitting ? 'Processing...' : 'Start AI Mapping'}
          </button>
        </div>
      </form>
    </div>
  );
};

export default AIMapping; 