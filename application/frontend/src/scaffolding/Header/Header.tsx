import './header.scss';

import { Menu, Search } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { Link, NavLink, useHistory, useLocation } from 'react-router-dom';
import { Button } from 'semantic-ui-react';

import { ClearFilterButton } from '../../components/FilterButton/FilterButton';
import { Capabilities } from '../../hooks/useCapabilities';
import { useLocationFromOutsideRoute } from '../../hooks/useLocationFromOutsideRoute';
import { SearchBar } from '../../pages/Search/components/SearchBar';
import { ROUTES } from '../../routes';

interface HeaderProps {
  capabilities: Capabilities;
}
export const Header = ({ capabilities }: HeaderProps) => {
  const routes = ROUTES(capabilities);

  let currentUrlParams = new URLSearchParams(window.location.search);
  const history = useHistory();
  const location = useLocation();
  const HandleDoFilter = () => {
    currentUrlParams.set('applyFilters', 'true');
    history.push(window.location.pathname + '?' + currentUrlParams.toString());
  };

  const isActive = (path: string, exact: boolean = false) => {
    if (exact) {
      return location.pathname === path;
    }
    return location.pathname.startsWith(path);
  };
  const { showFilter } = useLocationFromOutsideRoute(routes);

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
              <NavLink
                to="/"
                exact
                className="nav-link"
                activeClassName="nav-link--active"
                isActive={() => isActive('/', true)}
              >
                Home
              </NavLink>

              <NavLink
                to="/root_cres"
                className="nav-link"
                activeClassName="nav-link--active"
                isActive={() => isActive('/root_cres') || isActive('/node')}
              >
                Browse
              </NavLink>

              <NavLink
                to="/chatbot"
                className="nav-link"
                activeClassName="nav-link--active"
                isActive={() => isActive('/chatbot')}
              >
                Chat
              </NavLink>

              <NavLink
                to="/map_analysis"
                className="nav-link"
                activeClassName="nav-link--active"
                isActive={() => isActive('/map_analysis')}
              >
                Map Analysis
              </NavLink>

              <NavLink
                to="/explorer"
                className="nav-link"
                activeClassName="nav-link--active"
                isActive={() => isActive('/explorer')}
              >
                Explorer
              </NavLink>
              {capabilities.myopencre && (
                <NavLink
                  to="/myopencre"
                  className="nav-link"
                  activeClassName="nav-link--active"
                  isActive={() => isActive('/myopencre')}
                >
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
              {/* Left these divs so that we can add auth functionality directly here. */}
              {/* <div className="navbar__desktop-auth">
                <Link
                  to={{
                    pathname: '/auth',
                    state: { mode: 'login' },
                  }}
                  className="btn btn--ghost"
                >
                  Log In
                </Link>

                <Link
                  to={{
                    pathname: '/auth',
                    state: { mode: 'signup' },
                  }}
                  className="btn btn--primary"
                >
                  Sign Up
                </Link>
              </div> */}

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
            isActive={() => isActive('/', true)}
            onClick={closeMobileMenu}
          >
            Home
          </NavLink>

          <NavLink
            to="/root_cres"
            className="nav-link"
            activeClassName="nav-link--active"
            isActive={() => isActive('/root_cres') || isActive('/node')}
            onClick={closeMobileMenu}
          >
            Browse
          </NavLink>

          <NavLink
            to="/chatbot"
            className="nav-link"
            activeClassName="nav-link--active"
            isActive={() => isActive('/chatbot')}
            onClick={closeMobileMenu}
          >
            Chat
          </NavLink>

          <NavLink
            to="/map_analysis"
            className="nav-link"
            activeClassName="nav-link--active"
            isActive={() => isActive('/map_analysis')}
            onClick={closeMobileMenu}
          >
            Map Analysis
          </NavLink>

          <NavLink
            to="/explorer"
            className="nav-link"
            activeClassName="nav-link--active"
            isActive={() => isActive('/explorer')}
            onClick={closeMobileMenu}
          >
            Explorer
          </NavLink>
          {capabilities.myopencre && (
            <NavLink
              to="/myopencre"
              className="nav-link"
              activeClassName="nav-link--active"
              isActive={() => isActive('/myopencre')}
              onClick={closeMobileMenu}
            >
              MyOpenCRE
            </NavLink>
          )}
        </div>

        <div className="mobile-auth">
          {/* <div className="auth-buttons">
            <Link
              to={{
                pathname: '/auth',
                state: { mode: 'login' },
              }}
              className="btn btn--ghost"
              onClick={closeMobileMenu}
            >
              Log In
            </Link>

            <Link
              to={{
                pathname: '/auth',
                state: { mode: 'signup' },
              }}
              className="btn btn--primary"
              onClick={closeMobileMenu}
            >
              Sign Up
            </Link>
          </div> */}
        </div>
      </div>
    </>
  );
};
