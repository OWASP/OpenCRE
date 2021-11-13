import './header.scss';

import React, { useMemo, useState } from 'react';
import { Link, useHistory } from 'react-router-dom';
import { Menu, Button } from 'semantic-ui-react';

import { useLocationFromOutsideRoute } from '../../hooks/useLocationFromOutsideRoute';
import { SearchBar } from '../../pages/Search/components/SearchBar';

const getLinks = (): { to: string; name: string }[] => [
  {
    to: `/`,
    name: 'Open CRE',
  },
];

export const Header = () => {
const HandleDoFilter = () => {
    currentUrlParams.set("applyFilters", "true");
    history.push(window.location.pathname + "?" + currentUrlParams.toString());
  }

  const ClearFilter = () => {
    currentUrlParams.set("applyFilters", "false");
    currentUrlParams.delete('filters')
    history.push(window.location.pathname + "?" + currentUrlParams.toString());
  }

  const history = useHistory();

  let currentUrlParams = new URLSearchParams(window.location.search);
 

  const { params, url, showHeader, showFilter } = useLocationFromOutsideRoute();
  // console.log(useLocationFromOutsideRoute())
  const links = useMemo(() => getLinks(), [params]);

  if (!showHeader) {
    return null;
  }

  return (
    <div className="header">
      <Menu className="header__nav-bar" secondary>
        {links.map(({ to, name }) => (
          <Link
            key={name}
            className={`header__nav-bar__link ${url === to || true ? 'header__nav-bar__link--active' : ''}`}
            to={to}
          >
            <Menu.Item as="span" onClick={() => { }}>
              {name}
            </Menu.Item>
          </Link>
        ))}
        <Menu.Menu position="right">
          <Menu.Item>
            
            <SearchBar />

            {showFilter ? <div className="foo"><Button onClick={() => { HandleDoFilter() }} content="Apply Filters"></Button>
          <Button onClick={() => { ClearFilter() }} content="Clear Filters"></Button></div>
          : console.log(showFilter)}
          </Menu.Item>
        </Menu.Menu>
        

      </Menu>
    </div>
  );
};
