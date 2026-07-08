import './header.scss';

import { LogOut, Menu, Search, User, X } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { Link, useHistory } from 'react-router-dom';
import { NavLink } from 'react-router-dom';
import { Button } from 'semantic-ui-react';

import { ClearFilterButton } from '../../components/FilterButton/FilterButton';
import { Capabilities } from '../../hooks/useCapabilities';
import { useLocationFromOutsideRoute } from '../../hooks/useLocationFromOutsideRoute';
import { useUser } from '../../hooks/useUser';
import { SearchBar } from '../../pages/Search/components/SearchBar';
import { ROUTES } from '../../routes';

interface HeaderProps {
  capabilities: Capabilities;
}
export const Header = ({ capabilities }: HeaderProps) => {
  const routes = ROUTES(capabilities);

  let currentUrlParams = new URLSearchParams(window.location.search);
  const history = useHistory();
  const HandleDoFilter = () => {
    currentUrlParams.set('applyFilters', 'true');
    history.push(window.location.pathname + '?' + currentUrlParams.toString());
  };
  const { showFilter } = useLocationFromOutsideRoute(routes);

  const { user, isLoggedIn, loading: userLoading, login, logout } = useUser();

  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
  useEffect(() => {
    const mediaQuery = window.matchMedia('(min-width: 768px)');

    const handleBreakpointChange = (e: MediaQueryListEvent) => {
      if (e.matches) {
        setIsMobileMenuOpen(false);
      }
    };

    mediaQuery.addEventListener('change', handleBreakpointChange);

    return () => {
      mediaQuery.removeEventListener('change', handleBreakpointChange);
    };
  }, []);
  const closeMobileMenu = () => {
    setIsMobileMenuOpen(false);
  };

  return (
    <>
      <nav className="navbar">
        <div className="navbar__container">
          <div className="navbar__content">
            <Link to="/" className="navbar__logo">
              <img src="/logo.svg" alt="Logo" />
            </Link>

            <div className="navbar__desktop-links">
              <NavLink to="/" exact className="nav-link" activeClassName="nav-link--active">
                Home
              </NavLink>

              <NavLink to="/root_cres" className="nav-link" activeClassName="nav-link--active">
                Browse
              </NavLink>

              <NavLink to="/chatbot" className="nav-link" activeClassName="nav-link--active">
                Chat
              </NavLink>

              <NavLink to="/map_analysis" className="nav-link" activeClassName="nav-link--active">
                Map Analysis
              </NavLink>

              <NavLink to="/explorer" className="nav-link" activeClassName="nav-link--active">
                Explorer
              </NavLink>
              {capabilities.myopencre && (
                <NavLink to="/myopencre" className="nav-link" activeClassName="nav-link--active">
                  MyOpenCRE
                </NavLink>
              )}
            </div>

            <div>
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
            </div>

            <div className="navbar__actions">
              {capabilities.login && !userLoading && (
                <div className="navbar__desktop-auth">
                  {isLoggedIn ? (
                    <div className="user-info">
                      <div className="user-details">
                        <User className="icon" />
                        <span>{user}</span>
                      </div>
                      <Button onClick={logout}>
                        <LogOut className="icon" />
                        Logout
                      </Button>
                    </div>
                  ) : (
                    <Button onClick={login} content="Login" />
                  )}
                </div>
              )}

              <button className="navbar__mobile-menu-toggle" onClick={() => setIsMobileMenuOpen(true)}>
                <Menu className="icon" />
                <span className="sr-only">Toggle menu</span>
              </button>
            </div>
          </div>
        </div>
      </nav>

      <div className={`navbar__overlay ${isMobileMenuOpen ? 'is-open' : ''}`} onClick={closeMobileMenu}></div>

      <div className={`navbar__mobile-menu ${isMobileMenuOpen ? 'is-open' : ''}`}>
        <button
          className="navbar__mobile-menu-close"
          onClick={closeMobileMenu}
          aria-label="Close mobile menu"
        >
          <X className="mobile-close-icon" />
        </button>
        <div className="mobile-search-container">
          <SearchBar />
        </div>
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

        <div className="mobile-nav-links">
          <NavLink
            to="/"
            exact
            className="nav-link"
            activeClassName="nav-link--active"
            onClick={closeMobileMenu}
          >
            Home
          </NavLink>

          <NavLink
            to="/root_cres"
            className="nav-link"
            activeClassName="nav-link--active"
            onClick={closeMobileMenu}
          >
            Browse
          </NavLink>

          <NavLink
            to="/chatbot"
            className="nav-link"
            activeClassName="nav-link--active"
            onClick={closeMobileMenu}
          >
            Chat
          </NavLink>

          <NavLink
            to="/map_analysis"
            className="nav-link"
            activeClassName="nav-link--active"
            onClick={closeMobileMenu}
          >
            Map Analysis
          </NavLink>

          <NavLink
            to="/explorer"
            className="nav-link"
            activeClassName="nav-link--active"
            onClick={closeMobileMenu}
          >
            Explorer
          </NavLink>
          {capabilities.myopencre && (
            <NavLink
              to="/myopencre"
              className="nav-link"
              activeClassName="nav-link--active"
              onClick={closeMobileMenu}
            >
              MyOpenCRE
            </NavLink>
          )}
        </div>

        {capabilities.login && !userLoading && (
          <div className="mobile-auth">
            {isLoggedIn ? (
              <div className="user-info">
                <div className="user-details">
                  <User className="icon" />
                  <span>{user}</span>
                </div>
                <Button
                  onClick={() => {
                    closeMobileMenu();
                    logout();
                  }}
                >
                  <LogOut className="icon" />
                  Logout
                </Button>
              </div>
            ) : (
              <div className="auth-buttons">
                <Button
                  onClick={() => {
                    closeMobileMenu();
                    login();
                  }}
                  content="Login"
                />
              </div>
            )}
          </div>
        )}
      </div>
    </>
  );
};
