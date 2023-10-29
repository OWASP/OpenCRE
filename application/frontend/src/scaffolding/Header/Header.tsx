import './header.scss';

import React, { useMemo, useState } from 'react';
import { Link, useHistory } from 'react-router-dom';
import { Button, Menu } from 'semantic-ui-react';

import { ClearFilterButton } from '../../components/FilterButton/FilterButton';
import { useLocationFromOutsideRoute } from '../../hooks/useLocationFromOutsideRoute';
import { SearchBar } from '../../pages/Search/components/SearchBar';

const getLinks = (): { to: string; name: string }[] => [
  {
    to: `/`,
    name: 'Open CRE',
  },
  {
    to: `/chatbot`,
    name: 'OpenCRE Chat',
  },
  {
    to: `/map_analysis`,
    name: 'Map analysis',
  },
];

export const Header = () => {
  let currentUrlParams = new URLSearchParams(window.location.search);

  const HandleDoFilter = () => {
    currentUrlParams.set('applyFilters', 'true');
    history.push(window.location.pathname + '?' + currentUrlParams.toString());
    window.location.href = window.location.href;
  };

  const history = useHistory();

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
            <Menu.Item as="span" onClick={() => {}}>
              {name}
            </Menu.Item>
          </Link>
        ))}
        <Menu.Menu position="right">
          <Menu.Item>
            <SearchBar />

            {showFilter && currentUrlParams.has('showButtons') ? (
              <div className="foo">
                <Button
                  onClick={() => {
                    HandleDoFilter();
                  }}
                  content="Apply Filters"
                ></Button>
                <ClearFilterButton />
              </div>
            ) : (
              ''
            )}
          </Menu.Item>
        </Menu.Menu>
      </Menu>
    </div>
  );
};
