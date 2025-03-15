import './header.scss';

import { useAuth0 } from '@auth0/auth0-react';
import Cookies from 'js-cookie';
import React, { useEffect, useMemo, useState } from 'react';
import { Link, useHistory, useLocation } from 'react-router-dom';
import { Button, Menu, Modal } from 'semantic-ui-react';

import { ClearFilterButton } from '../../components/FilterButton/FilterButton';
import { LoadingAndErrorIndicator } from '../../components/LoadingAndErrorIndicator/LoadingAndErrorIndicator';
import ResourceSelection from '../../components/ResourceSelection/ResourceSelection';
import { useLocationFromOutsideRoute } from '../../hooks/useLocationFromOutsideRoute';
import { SearchBar } from '../../pages/Search/components/SearchBar';
import { useDataStore } from '../../providers/DataProvider';

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
  const { user, loginWithRedirect, isAuthenticated, logout } = useAuth0();
  const { setSelectedResources } = useDataStore();
  let currentUrlParams = new URLSearchParams(window.location.search);

  const HandleDoFilter = () => {
    currentUrlParams.set('applyFilters', 'true');
    history.push(window.location.pathname + '?' + currentUrlParams.toString());
  };

  const history = useHistory();
  const location = useLocation();
  const [showResourceModal, setShowResourceModal] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { params, url, showFilter } = useLocationFromOutsideRoute();
  const links = useMemo(() => getLinks(), [params]);

  const handleLogin = async () => {
    setLoading(true);
    setError(null);
    try {
      await loginWithRedirect({
        appState: { targetUrl: '/dashboard' },
      });
    } catch (err) {
      setError('Login failed. Please try again.');
      setLoading(false);
    }
  };

  const handleSaveResources = (resources: string[]) => {
    setSelectedResources(resources);
    setShowResourceModal(false);
  };

  useEffect(() => {
    if (isAuthenticated && location.pathname === '/dashboard') {
      const savedResources = Cookies.get('selectedResources')
        ? JSON.parse(Cookies.get('selectedResources')!)
        : null;
      if (savedResources) {
        setSelectedResources(savedResources);
      } else {
        setShowResourceModal(true);
      }
    }
  }, [isAuthenticated, location.pathname]);

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
        <Menu.Menu position="right">
          <Menu.Item>
            {isAuthenticated && location.pathname === '/dashboard' ? (
              <Button
                className="auth-button"
                onClick={() => {
                  logout();
                }}
                content="Logout"
              ></Button>
            ) : (
              !isAuthenticated && (
                <Button className="auth-button" onClick={handleLogin} content="Login"></Button>
              )
            )}
          </Menu.Item>
        </Menu.Menu>
      </Menu>

      <LoadingAndErrorIndicator loading={loading} error={error} />

      <Modal open={showResourceModal} onClose={() => setShowResourceModal(false)}>
        <Modal.Header>Select Resources</Modal.Header>
        <Modal.Content>
          <ResourceSelection onSave={handleSaveResources} />
        </Modal.Content>
      </Modal>
    </nav>
  );
};
