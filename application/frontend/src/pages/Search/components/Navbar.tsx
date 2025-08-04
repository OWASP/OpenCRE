import './navbar.scss';

import { Menu, Search } from 'lucide-react';
import React, { useState } from 'react';
import { Link } from 'react-router-dom';

import { useToast } from '../hooks/use-toast';

const Navbar = () => {
  const { toast } = useToast();
  const [searchQuery, setSearchQuery] = useState('');
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const handleSearch = (e: React.FormEvent) => {
    e.preventDefault();
    if (searchQuery.trim()) {
      toast({
        title: 'Search',
        description: `Searching for: ${searchQuery}`,
      });
      setSearchQuery('');
      setIsMobileMenuOpen(false);
    }
  };

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
              <Link to="/" className="nav-link">
                Home
              </Link>
              <a href="/browse" className="nav-link">
                Browse
              </a>
              <Link to="/chat" className="nav-link">
                Chat
              </Link>
              <a href="/map-analysis" className="nav-link">
                Map Analysis
              </a>
              <a href="/explorer" className="nav-link">
                Explorer
              </a>
            </div>

            <div className="navbar__search">
              <form onSubmit={handleSearch}>
                <Search className="search-icon" />
                <input
                  type="text"
                  placeholder="Search..."
                  value={searchQuery}
                  onChange={(e) => setSearchQuery(e.target.value)}
                />
              </form>
            </div>

            <div className="navbar__actions">
              <div className="navbar__desktop-auth">
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
              </div>

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
        <form onSubmit={handleSearch} className="mobile-search-form">
          <Search className="search-icon" />
          <input
            type="text"
            placeholder="Search..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
          />
        </form>

        <div className="mobile-nav-links">
          <Link to="/" className="nav-link" onClick={closeMobileMenu}>
            Home
          </Link>
          <a href="/browse" className="nav-link" onClick={closeMobileMenu}>
            Browse
          </a>
          <Link to="/chat" className="nav-link" onClick={closeMobileMenu}>
            Chat
          </Link>
          <a href="/map-analysis" className="nav-link" onClick={closeMobileMenu}>
            Map Analysis
          </a>
          <a href="/explorer" className="nav-link" onClick={closeMobileMenu}>
            Explorer
          </a>
        </div>

        <div className="mobile-auth">
          <div className="auth-buttons">
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
          </div>
        </div>
      </div>
    </>
  );
};

export default Navbar;
