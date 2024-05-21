import './search.scss';

import React from 'react';
import { Button, Header } from 'semantic-ui-react';

import { SearchBody } from './components/BodyText';

export const Search = () => {
  return (
    <div className="search-page">
      <div className="home-hero">
        <div className="hero-container">
          <Header as="h1" className="search-page__heading">
            Open Common Requirement Enumeration
          </Header>

          <Header as="h4" className="search-page__sub-heading">
            Your gateway to security topics
          </Header>
          <div>
            <Button primary fluid href="/root_cres" className="browse-button">
              Browse Topics
            </Button>
          </div>
        </div>
      </div>
      <SearchBody />
    </div>
  );
};
