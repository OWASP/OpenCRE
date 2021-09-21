import React, { useState } from 'react';
import { useHistory } from 'react-router-dom';
import { Button, Dropdown, Form, Icon, Input } from 'semantic-ui-react';

import { CRE, STANDARD, SEARCH } from '../../../routes';
import './SearchBar.scss'

const SEARCH_TYPES = [
  { key: 'topicText', text: 'Topic text', value: 'topicText' },
  { key: 'standard', text: 'Standard', value: 'standard' },
  { key: 'creId', text: 'CRE ID', value: 'creId' },
];

interface SearchBarState {
  term: string;
  type: string;
  error: string;
}

const DEFAULT_SEARCH_BAR_STATE: SearchBarState = { term: '', type: SEARCH_TYPES[0].key, error: '' };

export const SearchBar = () => {
  const [search, setSearch] = useState<SearchBarState>(DEFAULT_SEARCH_BAR_STATE);
  const history = useHistory();

  const onSubmit = () => {
    var path
    if (Boolean(search.term)) {
      if (search.type == "topicText") {
        path = SEARCH
      } else if (search.type === 'standard') {
        path = STANDARD
      } else if (search.type == 'creId') {
        path = CRE
      }
      setSearch(DEFAULT_SEARCH_BAR_STATE);
      history.push(`${path}/${search.term}`);
      window.location.href = window.location.href // horrible hack, but on the search results page
                                                 //react will not do any requests otherwise
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

    <Form
      onSubmit={onSubmit}
    >
      <Form.Group>
        <Form.Field
          id="SearchBar">
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
                options={SEARCH_TYPES}
                value={search.type}
                onChange={onChange}
              />
            }
            labelPosition="right"
            placeholder="Search..."
          />
        </Form.Field>
        <Form.Field
          id="SearchButton">
          <Button
            primary
            onSubmit={onSubmit}>
            <Icon name="search" />
            Search
          </Button>
        </Form.Field>
      </Form.Group>
    </Form>

  );
};
