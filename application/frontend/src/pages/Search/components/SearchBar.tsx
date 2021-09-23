import React, { useState } from 'react';
import { useHistory } from 'react-router-dom';
import { Button, Dropdown, Form, Icon, Input } from 'semantic-ui-react';

import { CRE, SEARCH, STANDARD } from '../../../const';

import './SearchBar.scss'

const SEARCH_TYPES = {
  topicText: { key: 'topicText', text: 'Topic text', value: 'topicText', path: SEARCH },
  standard: { key: 'standard', text: 'Standard', value: 'standard', path: STANDARD },
  creId: { key: 'creId', text: 'CRE ID', value: 'creId', path: CRE  },
};

interface SearchBarState {
  term: string;
  type: string;
  error: string;
}

const DEFAULT_SEARCH_BAR_STATE: SearchBarState = { term: '', type: SEARCH_TYPES['topicText'].key, error: '' };

export const SearchBar = () => {
  const [search, setSearch] = useState<SearchBarState>(DEFAULT_SEARCH_BAR_STATE);
  const history = useHistory();

  const onSubmit = () => {
    const {term, type} = search;

    if (Boolean(search.term)) {
      setSearch(DEFAULT_SEARCH_BAR_STATE);
      history.push(`${SEARCH_TYPES[type].path}/${term}`);
    } else {
      setSearch({
        ...search,
        error: 'Search term cannot be blank',
      });
    }
  }

  const onChange = (_, { value }) => {
    setSearch({
      ...search,
      type: value as string,
    });
  }

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
            label={
              <Dropdown
                options={Object.values(SEARCH_TYPES)}
                value={search.type}
                onChange={onChange}
              />
            }
            labelPosition="right"
            placeholder="Search..."
          />
        </Form.Field>
        <Form.Field id="SearchButton">
          <Button
            primary
            onSubmit={onSubmit}
          >
            <Icon name="search" />
            Search
          </Button>
        </Form.Field>
      </Form.Group>
    </Form>
  );
};
