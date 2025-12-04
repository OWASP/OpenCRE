import './header.scss';

import { Menu, Search } from 'lucide-react';
import React, { useState } from 'react';
import { Link, useHistory, useLocation } from 'react-router-dom';
import { Button } from 'semantic-ui-react';

import { ClearFilterButton } from '../../components/FilterButton/FilterButton';
import { useLocationFromOutsideRoute } from '../../hooks/useLocationFromOutsideRoute';
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

  const closeMobileMenu = () => {
    setIsMobileMenuOpen(false);
  };



  const location = useLocation();
  const currentPath = location.pathname;
  const isActive = (path: string) => currentPath === path;



  return (
    <>
      <nav className="navbar">
        <div className="navbar__container">
          <div className="navbar__content">
            <Link to="/" className="navbar__logo">
              <img src="/logo.svg" alt="Logo" />
            </Link>

            <div className="navbar__desktop-links">
  <Link 
    to="/" 
    className={`nav-link ${isActive('/') ? 'active' : ''}`}
  >
    Home
  </Link>

  <a 
    href="/root_cres" 
    className={`nav-link ${isActive('/root_cres') ? 'active' : ''}`}
  >
    Browse
  </a>

  <Link 
    to="/chatbot" 
    className={`nav-link ${isActive('/chatbot') ? 'active' : ''}`}
  >
    Chat
  </Link>

  <a 
    href="/map_analysis" 
    className={`nav-link ${isActive('/map_analysis') ? 'active' : ''}`}
  >
    Map Analysis
  </a>

  <a 
    href="/explorer" 
    className={`nav-link ${isActive('/explorer') ? 'active' : ''}`}
  >
    Explorer
  </a>
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
          <Link to="/" className="nav-link" onClick={closeMobileMenu}>
            Home
          </Link>
          <a href="/root_cres" className="nav-link" onClick={closeMobileMenu}>
            Browse
          </a>
          <Link to="/chatbot" className="nav-link" onClick={closeMobileMenu}>
            Chat
          </Link>
          <a href="/map_analysis" className="nav-link" onClick={closeMobileMenu}>
            Map Analysis
          </a>
          <a href="/explorer" className="nav-link" onClick={closeMobileMenu}>
            Explorer
          </a>
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
