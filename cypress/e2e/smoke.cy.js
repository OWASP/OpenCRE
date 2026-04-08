describe('OpenCRE e2e smoke', () => {
  it('loads homepage with primary search form', () => {
    cy.visit('/');
    cy.get('form#search-bar').should('exist');
    cy.get('form#search-bar input[type="text"]').should('be.visible');
  });

  it('home search routes to search results page', () => {
    const term = 'asvs';
    cy.visit('/');
    cy.get('form#search-bar input[type="text"]').type(`${term}{enter}`);
    cy.url().should('include', `/search/${term}`);
    cy.contains('Results matching').should('be.visible');
  });

  it('browse route is reachable', () => {
    cy.visit('/root_cres');
    cy.contains('h1', 'Root CREs').should('be.visible');
  });
});
