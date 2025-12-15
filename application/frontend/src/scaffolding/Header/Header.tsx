import { Menu, Search, X } from 'lucide-react';
import React, { useState } from 'react';
import { Link, useHistory } from 'react-router-dom';
import { ClearFilterButton } from '../../components/FilterButton/FilterButton';
import { useLocationFromOutsideRoute } from '../../hooks/useLocationFromOutsideRoute';
import { SearchBar } from '../../pages/Search/components/SearchBar';

export const Header = () => {
  const history = useHistory();
  const { showFilter } = useLocationFromOutsideRoute();
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);

  const toggleMobileMenu = () => setIsMobileMenuOpen(v => !v);
  const closeMobileMenu = () => setIsMobileMenuOpen(false);

  // read current url params (note: using window is fine here in client)
  let currentUrlParams = new URLSearchParams(window.location.search);
  const handleDoFilter = () => {
    currentUrlParams.set('applyFilters', 'true');
    history.push(window.location.pathname + '?' + currentUrlParams.toString());
  };

  const navLinkClass = 'text-muted-foreground hover:text-foreground transition-colors text-lg font-medium';
  const btnPrimary = 'px-4 py-2 rounded-md border-none cursor-pointer transition-all bg-white text-black hover:bg-gray-200 shadow-lg';

  return (
    <>
      <nav
        className="sticky top-0 z-50 w-full border-b border-white/20 text-foreground shadow-xl"
        style={{
          backgroundColor: 'rgb(2, 8, 23)',
          color: 'rgb(222, 222, 227)',
          backdropFilter: 'blur(8px)',
        }}
        aria-label="Main navigation"
      >
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <div className="flex justify-between items-center h-16">

            <Link to="/" className="flex items-center gap-2">
              <img
                src="/logo.svg"
                alt="Logo"
                className="h-10 w-auto object-contain"
              />
            </Link>

            <div className="hidden lg:flex items-center gap-4 xl:gap-8 mx-auto">
              <Link to="/" className={navLinkClass}>Home</Link>
              <a href="/root_cres" className={navLinkClass}>Browse</a>
              <Link to="/chatbot" className={navLinkClass}>Chat</Link>
              <a href="/map_analysis" className={navLinkClass}>Map Analysis</a>
              <a href="/explorer" className={navLinkClass}>Explorer</a>
            </div>

            <div className="flex items-center gap-4">

              {/* Desktop / Laptop search: visible on md and up */}
              <div className="hidden md:block min-w-[320px]">
                {/* ensure SearchBar itself uses width: w-full internally; this wrapper gives it space */}
                <SearchBar />
                {showFilter && currentUrlParams.has('showButtons') && (
                  <div className="flex gap-2 mt-2">
                    <button onClick={handleDoFilter} className={btnPrimary}>Apply Filters</button>
                    <ClearFilterButton />
                  </div>
                )}
              </div>

              {/* Mobile menu button (visible on small screens) */}
              <button
                className="md:hidden bg-transparent p-2 rounded-md hover:bg-white/10 transition"
                onClick={toggleMobileMenu}
                aria-expanded={isMobileMenuOpen}
                aria-label="Open menu"
              >
                <Menu className="h-6 w-6 text-foreground" />
              </button>
            </div>

          </div>
        </div>
      </nav>

      {/* overlay */}
      <div
        className={`fixed inset-0 z-40 bg-black/50 transition-opacity duration-300 ${isMobileMenuOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'}`}
        onClick={closeMobileMenu}
        aria-hidden={!isMobileMenuOpen}
      />

      {/* mobile slide-over */}
      <aside
        className={`fixed top-0 right-0 h-full z-50 transform transition-transform duration-300 ease-in-out
                    w-72 sm:w-[400px] bg-[#020817] border-l border-gray-700 p-4 flex flex-col gap-4
                    ${isMobileMenuOpen ? 'translate-x-0' : 'translate-x-full'}`}
        role="dialog"
        aria-modal="true"
        style={{ color: 'rgb(222, 222, 227)' }}
      >

        <div className="flex justify-end mb-2">
          <button onClick={closeMobileMenu} className="p-2 rounded-md hover:bg-white/10" aria-label="Close menu">
            <X className="h-6 w-6 text-foreground" />
          </button>
        </div>

        {/* Mobile search (visible inside slide-over) */}
        <div className="w-full mb-2">
          <SearchBar />
          {showFilter && currentUrlParams.has('showButtons') && (
            <div className="flex flex-col gap-2 mt-2">
              <button
                onClick={() => {
                  handleDoFilter();
                  closeMobileMenu();
                }}
                className={`${btnPrimary} w-full text-left justify-start`}
              >
                Apply Filters
              </button>
              <ClearFilterButton />
            </div>
          )}
        </div>

        <nav className="flex flex-col gap-2">
          <Link to="/" className={`${navLinkClass} p-2 rounded-md hover:bg-white/5 text-lg`} onClick={closeMobileMenu}>Home</Link>
          <a href="/root_cres" className={`${navLinkClass} p-2 rounded-md hover:bg-white/5 text-lg`} onClick={closeMobileMenu}>Browse</a>
          <Link to="/chatbot" className={`${navLinkClass} p-2 rounded-md hover:bg-white/5 text-lg`} onClick={closeMobileMenu}>Chat</Link>
          <a href="/map_analysis" className={`${navLinkClass} p-2 rounded-md hover:bg-white/5 text-lg`} onClick={closeMobileMenu}>Map Analysis</a>
          <a href="/explorer" className={`${navLinkClass} p-2 rounded-md hover:bg-white/5 text-lg`} onClick={closeMobileMenu}>Explorer</a>
        </nav>

        <div className="mt-auto border-t border-gray-700 pt-4 flex flex-col gap-3">
          {/* footer actions / links can go here */}
        </div>

      </aside>
    </>
  );
};
