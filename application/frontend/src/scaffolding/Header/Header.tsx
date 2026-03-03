import './header.scss';

import { Menu, Search } from 'lucide-react';
import React, { useEffect, useState } from 'react';
import { Link, useHistory } from 'react-router-dom';
import { NavLink } from 'react-router-dom';
import { Button } from 'semantic-ui-react';

import { ClearFilterButton } from '../../components/FilterButton/FilterButton';
import { useLocationFromOutsideRoute } from '../../hooks/useLocationFromOutsideRoute';
import { MyOpenCRE } from '../../pages/MyOpenCRE/MyOpenCRE';
import { SearchBar } from '../../pages/Search/components/SearchBar';

export const Header = () => {
  let currentUrlParams = new URLSearchParams(window.location.search);
  const history = useHistory();
  const HandleDoFilter = () => {
    currentUrlParams.set('applyFilters', 'true');
    history.push(window.location.pathname + '?' + currentUrlParams.toString());
  };
  const { showFilter } = useLocationFromOutsideRoute();

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
              <NavLink to="/myopencre" className="nav-link" activeClassName="nav-link--active">
                MyOpenCRE
              </NavLink>
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
          <NavLink
            to="/myopencre"
            className="nav-link"
            activeClassName="nav-link--active"
            onClick={closeMobileMenu}
          >
            MyOpenCRE
          </NavLink>
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
