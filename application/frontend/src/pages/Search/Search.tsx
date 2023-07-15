import './search.scss';

import React from 'react';
import { Button, Header } from 'semantic-ui-react';

import { SearchBody } from './components/BodyText';
import { SearchBar } from './components/SearchBar';

export const Search = () => {
  return (
    <div className="search-page">
      <Header as="h1" className="search-page__heading">
        Open Common Requirement Enumeration
      </Header>

      <Header as="h4" className="search-page__sub-heading">
        Your gateway to security topics
      </Header>
      <div>
        <SearchBar />
        <Button primary fluid href="/root_cres">
          Browse Topics
        </Button>
      </div>
      <SearchBody />
    </div>
  );
};
