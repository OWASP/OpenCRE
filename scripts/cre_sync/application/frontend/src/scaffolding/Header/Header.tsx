import './header.scss';

import React, { useMemo } from 'react';
import { Link } from 'react-router-dom';
import { Menu } from 'semantic-ui-react';

import { useLocationFromOutsideRoute } from '../../hooks/useLocationFromOutsideRoute';
import { SearchBar } from '../../pages/Search/components/SearchBar';

const getLinks = (): { to: string; name: string }[] => [
  {
    to: `#`,
    name: 'Document View',
  },
];

export const Header = () => {
  const { params, url, showHeader } = useLocationFromOutsideRoute();
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
          </Menu.Item>
        </Menu.Menu>
      </Menu>
    </div>
  );
};
