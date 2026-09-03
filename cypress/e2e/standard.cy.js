describe('OpenCRE standard browse', () => {
  it('renders the ASVS standard page with heading, sections and pagination', () => {
    cy.visit('/node/standard/ASVS');
    cy.contains('h4.standard-page__heading', 'ASVS').should('be.visible');
    cy.get('.accordion').should('have.length.greaterThan', 0);
    cy.get('.pagination').should('exist');

    // Expand the first accordion and verify it becomes visible (content appears).
    cy.get('.accordion .title.document-node').first().click();
    cy.get('.accordion .content').first().should('be.visible');

    // Click pagination and verify content changes.
    cy.get('.accordion')
      .first()
      .invoke('text')
      .then((firstPageText) => {
        cy.get('.pagination').contains('2').click();
        cy.get('.accordion').first().invoke('text').should('not.eq', firstPageText);
      });
  });
});