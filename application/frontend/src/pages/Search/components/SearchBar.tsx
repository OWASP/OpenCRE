import './SearchBar.scss';

import React, { useState } from 'react';
import { useHistory } from 'react-router-dom';
import { Button, Form, Icon, Input } from 'semantic-ui-react';

import { SEARCH } from '../../../const';

interface SearchBarState {
  term: string;
  error: string;
}

const DEFAULT_SEARCH_BAR_STATE: SearchBarState = { term: '', error: '' };

export const SearchBar = () => {
  const [search, setSearch] = useState<SearchBarState>(DEFAULT_SEARCH_BAR_STATE);
  const history = useHistory();

  const onSubmit = () => {
    const { term } = search;

    if (Boolean(search.term)) {
      setSearch(DEFAULT_SEARCH_BAR_STATE);
      history.push(`${SEARCH}/${term}`);
    } else {
      setSearch({
        ...search,
        error: 'Search term cannot be blank',
      });
    }
  };

  return (
    <Form onSubmit={onSubmit}>
      <Form.Group>
        <Form.Field id="SearchBar">
          <Input
            error={Boolean(search.error)}
            value={search.term}
            onChange={(e) => {
              setSearch({
                ...search,
                term: e.target.value,
              });
            }}
            action={{
              icon: 'search',
              content: 'Search',
              color: 'blue',
            }}
            placeholder="Search..."
          />
        </Form.Field>
      </Form.Group>
    </Form>
  );
};
