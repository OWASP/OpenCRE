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

  return (
    <div className="navbar__search">
      <form onSubmit={onSubmit}>
        <Search className="search-icon" />

        <input
          type="text"
          placeholder="Search..."
          value={search.term}
          onChange={(e) =>
            setSearch({
              ...search,
              term: e.target.value,
            })
          }
        />
      </form>

      {/* Error text */}
      {search.error && <p className="search-error">{search.error}</p>}
    </div>
  );
};
