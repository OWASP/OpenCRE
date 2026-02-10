import './SearchBar.scss';

import { Search } from 'lucide-react';
import React, { useState } from 'react';
import { useHistory } from 'react-router-dom';

import { SEARCH } from '../../../const';

interface SearchBarState {
  term: string;
  error: string;
}

const DEFAULT_SEARCH_BAR_STATE: SearchBarState = { term: '', error: '' };

export const SearchBar = () => {
  const [search, setSearch] = useState<SearchBarState>(DEFAULT_SEARCH_BAR_STATE);
  const history = useHistory();

  const onSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const { term } = search;

    if (term.trim()) {
      setSearch(DEFAULT_SEARCH_BAR_STATE);
      history.push(`${SEARCH}/${term}`);
    } else {
      setSearch({
        ...search,
        error: 'Search term cannot be blank',
      });
    }
  };

  const inputId = 'navbar-search-input';
  const errorId = 'navbar-search-error';
  return (
    <div className="navbar__search">
      <form onSubmit={onSubmit}>
        <label htmlFor={inputId} className="visually-hidden">
          Search OpenCRE
        </label>

        <Search className="search-icon" aria-hidden="true" />

        <input
          id={inputId}
          type="text"
          placeholder="Search..."
          value={search.term}
          aria-label="Search OpenCRE"
          aria-invalid={Boolean(search.error)}
          aria-describedby={search.error ? errorId : undefined}
          onChange={(e) =>
            setSearch({
              ...search,
              term: e.target.value,
            })
          }
        />
      </form>

      {search.error && (
        <p
          id={errorId}
          className="search-error"
          role="alert"
        >
          {search.error}
        </p>
      )}
    </div>
  );
};
