import { Search } from 'lucide-react';
import React, { useState } from 'react';
import { useHistory } from 'react-router-dom';

// import { SEARCH } from '../../../const';

interface SearchBarState {
  term: string;
  error: string;
}

const DEFAULT_SEARCH_BAR_STATE: SearchBarState = { term: '', error: '' };

const SEARCH = '/search-results';

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
    <div className="hidden items-center lg:flex">
      <form onSubmit={onSubmit} className="relative">

        <Search
          className="
            absolute 
            left-3 
            top-1/2 
            -translate-y-1/2 
            text-gray-400 
            h-4 w-4
          "
        />

        <input
          type="text"
          placeholder="Search..."
          value={search.term}
          onChange={(e) =>
            setSearch({
              ...search,
              error: '',
              term: e.target.value,
            })
          }
          style={{ border: "1px solid gray" }}
          className="
            py-2 
            px-4 
            pl-10           
            w-64 
            bg-transparent  
            border-1       
            rounded-full     
            text-foreground   
          "
        />
      </form>

      {search.error && (
        <p className="mt-1 text-xs text-red-400">{search.error}</p>
      )}
    </div>
  );
};