describe('OpenCRE standard browse', () => {
  it('renders the ASVS standard page with heading, sections and pagination', () => {
    cy.visit('/node/standard/ASVS');
    // Heading is the standard id.
    cy.contains('h4.standard-page__heading', 'ASVS').should('be.visible');
    // Data-bearing: at least one section accordion renders from real data.
    cy.get('.accordion').should('have.length.greaterThan', 0);
    // Semantic-ui pagination is present for a multi-section standard.
    cy.get('.pagination').should('exist');
  });
});
