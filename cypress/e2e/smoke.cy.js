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
    // #mount is the scroll container (body is overflow:hidden). scrollIntoView
    // keeps this assertion robust if SPA navigation left #mount mid-scroll.
    cy.contains('Results matching').scrollIntoView().should('be.visible');
  });

  it('browse route is reachable', () => {
    cy.visit('/root_cres');
    cy.contains('h1', 'Root CREs').scrollIntoView().should('be.visible');
    // Data-bearing: the fixture root CRE 558-807 renders in the list
    // (scripts/seed_e2e_fixtures.py). Do not swap this for "Cryptography" —
    // that CRE is the free-text search fixture, not the root-CRE contract.
    cy.get('.standard-page__links-container').should('contain.text', 'Mutually authenticate');
  });
});
