import React, { useState } from 'react';
import { useHistory } from 'react-router-dom';
import { Button, Dropdown, Form, Icon, Input } from 'semantic-ui-react';

import { CRE, STANDARD } from '../../../routes';

const SEARCH_TYPES = [
  { key: 'standard', text: 'Standard', value: 'standard' },
  { key: 'creId', text: 'CRE ID', value: 'creId' },
  // { key: 'creName', text: 'CRE Name', value: 'creName' },
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

  return (
    <Form>
      <Form.Group>
        <Form.Field>
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
                onChange={(_, { value }) => {
                  setSearch({
                    ...search,
                    type: value as string,
                  });
                }}
              />
            }
            labelPosition="right"
            placeholder="Search..."
          />
        </Form.Field>
        <Form.Field>
          <Button
            primary
            onClick={() => {
              if (Boolean(search.term)) {
                const path = search.type === 'standard' ? STANDARD : CRE;
                setSearch(DEFAULT_SEARCH_BAR_STATE);
                history.push(`${path}/${search.term}`);
              } else {
                setSearch({
                  ...search,
                  error: 'Search term cannot be blank',
                });
              }
            }}
          >
            <Icon name="search" />
            Search
          </Button>
        </Form.Field>
      </Form.Group>
    </Form>
  );
};
