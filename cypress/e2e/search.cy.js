describe('OpenCRE search results', () => {
  it('shows a no-results message for a term that matches nothing', () => {
    const term = 'asdf';
    cy.visit('/');
    cy.get('form#search-bar input[type="text"]').type(`${term}{enter}`);
    cy.url().should('include', `/search/${term}`);
    cy.contains('No results match your search term').should('be.visible');
  });

  it('returns matching results for a real free-text query', () => {
    const term = 'crypto';
    cy.visit('/');
    cy.get('form#search-bar input[type="text"]').type(`${term}{enter}`);
    cy.url().should('include', `/search/${term}`);
    // Data-bearing: a populated backend renders a "Matching CREs" section.
    // This fails (red) if the DB is empty or the search API returns 500.
    cy.contains('h1', 'Matching CREs').should('be.visible');
  });
});
