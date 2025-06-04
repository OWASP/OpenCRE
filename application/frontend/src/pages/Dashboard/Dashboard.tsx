import { useAuth0 } from '@auth0/auth0-react';
import Cookies from 'js-cookie';
import { useEffect, useMemo } from 'react';
import React, { useState } from 'react';
import { Button, Header, Modal } from 'semantic-ui-react';

import ResourceSelection from '../../components/ResourceSelection/ResourceSelection';
import { useDataStore } from '../../providers/DataProvider';

export const Dashboard = () => {
  console.log('Dashboard component rendered'); // Add this line for debugging

  const { user, loginWithRedirect, isAuthenticated, logout } = useAuth0();
  const [showResourceModal, setShowResourceModal] = useState(false);
  const { setSelectedResources } = useDataStore();

  const handleSaveResources = (resources: string[]) => {
    setSelectedResources(resources);
    Cookies.set('selectedResources', JSON.stringify(resources), { expires: 365 });
    setShowResourceModal(false);
  };

  return (
    <div className="search-page">
      <div className="home-hero">
        <div className="hero-container">
          <Header as="h1" className="search-page__heading">
            User Dashboard
          </Header>

          <Header as="h4" className="search-page__sub-heading">
            Your personal space
          </Header>
          <div>
            <Button primary fluid className="browse-button" onClick={() => setShowResourceModal(true)}>
              Select Resources
            </Button>
          </div>
        </div>
      </div>
      <Modal open={showResourceModal} onClose={() => setShowResourceModal(false)}>
        <Modal.Header>Select Resources</Modal.Header>
        <Modal.Content>
          <ResourceSelection onSave={handleSaveResources} />
        </Modal.Content>
      </Modal>
    </div>
  );
};
