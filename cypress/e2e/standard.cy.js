describe('OpenCRE standard browse', () => {
  it('renders the ASVS standard page with heading, sections and pagination', () => {
    cy.visit('/node/standard/ASVS');
    // Heading is the standard id.
    cy.contains('h4.standard-page__heading', 'ASVS').should('be.visible');
    // Data-bearing: at least one section accordion renders from real data.
    cy.get('.accordion').should('have.length.greaterThan', 0);
    // Semantic-ui pagination is present for a multi-section standard.
    cy.get('.pagination').should('exist');

    // Expand the first accordion and verify its content becomes visible.
    // This ensures that the UI can render details without relying on a
    // specific section ID that may change.
    cy.get('.accordion .title.document-node').first().click();
    cy.get('.accordion .content').first().should('be.visible');

    // Clicking pagination changes the rendered content.
    cy.get('.accordion')
      .first()
      .invoke('text')
      .then((firstPageText) => {
        cy.get('.pagination').contains('2').click();
        cy.get('.accordion').first().invoke('text').should('not.eq', firstPageText);
      });
  });
});