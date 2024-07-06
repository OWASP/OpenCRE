import './header.scss';

import React, { useMemo } from 'react';
import { Link, useHistory } from 'react-router-dom';
import { Button, Menu } from 'semantic-ui-react';

import { ClearFilterButton } from '../../components/FilterButton/FilterButton';
import { useLocationFromOutsideRoute } from '../../hooks/useLocationFromOutsideRoute';
import { SearchBar } from '../../pages/Search/components/SearchBar';

const getLinks = (): { to: string; name: string }[] => [
  {
    to: `/`,
    name: 'Home',
  },
  {
    to: `/root_cres`,
    name: 'Browse',
  },
  {
    to: `/chatbot`,
    name: 'OpenCRE Chat',
  },
  {
    to: `/map_analysis`,
    name: 'Map Analysis',
  },
  // {
  //   to: `/explorer`,
  //   name: 'OpenCRE Explorer',
  // },
];

export const Header = () => {
  let currentUrlParams = new URLSearchParams(window.location.search);

  const HandleDoFilter = () => {
    currentUrlParams.set('applyFilters', 'true');
    history.push(window.location.pathname + '?' + currentUrlParams.toString());
  };

  const history = useHistory();

  const { params, url, showFilter } = useLocationFromOutsideRoute();
  // console.log(useLocationFromOutsideRoute())
  const links = useMemo(() => getLinks(), [params]);

  return (
    <nav className="header">
      <Menu className="header__nav-bar" secondary>
        <Link to="/" className="header__nav-bar-logo">
          <img alt="Open CRE" src="/logo_dark_nobyline.svg" />
        </Link>
        <Menu.Menu position="left">
          {links.map(({ to, name }) => (
            <Link
              key={name}
              className={`header__nav-bar__link ${url === to ? 'header__nav-bar__link--active' : ''}`}
              to={to}
            >
              <Menu.Item as="span" onClick={() => {}}>
                {name}
              </Menu.Item>
            </Link>
          ))}
        </Menu.Menu>
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
    </nav>
  );
};
