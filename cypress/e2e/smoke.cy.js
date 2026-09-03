describe('OpenCRE e2e smoke', () => {
  it('loads homepage with primary search form', () => {
    cy.visit('/');
    cy.get('form#search-bar').should('exist');
    cy.get('form#search-bar input[type="text"]').should('be.visible');
    cy.contains('form#search-bar button[type="submit"]', 'Search').should('be.visible');
  });

  it('home search routes to search results page', () => {
    const term = 'asvs';
    cy.visit('/');
    cy.get('form#search-bar input[type="text"]').type(`${term}{enter}`);
    cy.url().should('include', `/search/${term}`);
    cy.contains('Results matching').scrollIntoView().should('be.visible');  // <-- changed
  });

  it('browse route is reachable', () => {
    cy.visit('/root_cres');
    cy.contains('h1', 'Root CREs').should('be.visible');
    cy.get('.standard-page__links-container').should('contain.text', 'Cryptography'); // <-- changed
  });
});