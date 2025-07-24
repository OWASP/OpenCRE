import React, { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import './aiMapping.scss';
import './aiComplete.scss';

export const AIComplete: React.FC = () => {
  const [success, setSuccess] = useState<boolean>(true);
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    // Could fetch final status from the server if needed
    const searchParams = new URLSearchParams(window.location.search);
    if (searchParams.get('error')) {
      setSuccess(false);
      setMessage(searchParams.get('error'));
    } else {
      setMessage(searchParams.get('message'));
    }
  }, []);

  return (
    <div className="ai-complete-container">
      <div className="ai-complete-card">
        <div className="ai-complete-icon">
          {success ? (
            <i className="ai-complete-success-icon">✓</i>
          ) : (
            <i className="ai-complete-error-icon">!</i>
          )}
        </div>
        
        <h1>{success ? 'AI Mapping Complete' : 'Mapping Error'}</h1>
        
        <p className="ai-complete-message">
          {message || (success 
            ? 'Your mappings have been saved successfully. You can now view them in the system.' 
            : 'There was an error processing your mapping request.'
          )}
        </p>

        <div className="ai-complete-card-content">
          <h2>What's Next?</h2>
          <p>
            {success 
              ? 'The approved mappings have been saved to the database. You can now:' 
              : 'You can try again or explore other options:'
            }
          </p>
          <ul>
            <li>Browse the mappings in the standard view</li>
            <li>Explore related CREs in the graph view</li>
            <li>Use the mappings for gap analysis</li>
            <li>Export the mappings for your documentation</li>
          </ul>
        </div>

        <div className="ai-complete-actions">
          <Link to="/myopencre/ai-map" className="ai-complete-button primary">
            Map Another Standard
          </Link>
          <Link to="/graph" className="ai-complete-button secondary">
            Explore in Graph View
          </Link>
          <Link to="/" className="ai-complete-button outline">
            Return to Home
          </Link>
        </div>
      </div>
    </div>
  );
};

export default AIComplete; 