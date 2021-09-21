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

  const onClick = () => {
    if (Boolean(search.term)) {
      if (search.type == "topicText") {
        history.push(`${SEARCH}/${search.term}`);
        return;
      }
      const path = search.type === 'standard' ? STANDARD : CRE;
      setSearch(DEFAULT_SEARCH_BAR_STATE);
      history.push(`${path}/${search.term}`);
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
    <Form>
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
            onClick={onClick}>
            <Icon name="search" />
            Search
          </Button>
        </Form.Field>
      </Form.Group>
    </Form>
  );
};
