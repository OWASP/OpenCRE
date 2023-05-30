import './search.scss';

import React from 'react';
import { Header } from 'semantic-ui-react';

import { SearchBody } from './components/BodyText';
import { SearchBar } from './components/SearchBar';

export const Search = () => {
  return (
    <div className="search-page">
      <Header as="h1" className="search-page__heading">
        Common Requirement Enumeration
      </Header>

      <Header as="h4" className="search-page__sub-heading">
        Your gateway to security topics
      </Header>
      <SearchBar />
      <SearchBody />
    </div>
  );
};
