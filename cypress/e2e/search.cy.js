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
    // The "Matching CREs" heading renders even with zero results, so assert
    // the actual result row (fixture CRE 170-772 "Cryptography") instead.
    cy.get('.standard-page__links-container').should('contain.text', 'Cryptography');
  });
});
