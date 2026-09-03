describe('OpenCRE e2e smoke', () => {
  it('loads homepage with primary search form', () => {
    cy.visit('/');
    cy.get('form#search-bar').should('exist');
    cy.get('form#search-bar input[type="text"]').should('be.visible');
    // Historical Jest coverage asserted the search UI "contains Search".
    cy.contains('form#search-bar button[type="submit"]', 'Search').should('be.visible');
  });

  it('home search routes to search results page', () => {
    const term = 'asvs';
    cy.visit('/');
    cy.get('form#search-bar input[type="text"]').type(`${term}{enter}`);
    cy.url().should('include', `/search/${term}`);
    // Ensure the heading is scrolled into view (fixes clipping in some containers).
    cy.contains('Results matching').scrollIntoView().should('be.visible');
  });

  it('browse route is reachable', () => {
    cy.visit('/root_cres');
    cy.contains('h1', 'Root CREs').should('be.visible');
    // Data-bearing: at least one root CRE is rendered; we check for a known
    // fixture entry that is stable across test runs.
    cy.get('.standard-page__links-container').should('contain.text', 'Cryptography');
  });
});