describe('OpenCRE standard browse', () => {
  it('renders the ASVS standard page with heading, sections and pagination', () => {
    cy.visit('/node/standard/ASVS');
    // Heading is the standard id.
    cy.contains('h4.standard-page__heading', 'ASVS').should('be.visible');
    // Data-bearing: at least one section accordion renders from real data.
    cy.get('.accordion').should('have.length.greaterThan', 0);
    // Semantic-ui pagination is present for a multi-section standard.
    cy.get('.pagination').should('exist');

    // ASVS/V13.2.5 (owned by scripts/seed_e2e_fixtures.py) sorts first and
    // is linked to CRE 558-807. Its content (external reference + CRE link)
    // lives in a collapsed accordion panel, so expand it first.
    cy.contains('.title.document-node', 'V13.2.5').should('be.visible').click();
    cy.contains('a[href="https://example.com/asvs/v13.2.5"]', 'https://example.com/asvs/v13.2.5').should(
      'be.visible'
    );
    // Expanding it follows through to the linked CRE.
    cy.get('a[href="/cre/558-807"]').should('exist');

    // Clicking pagination actually changes the rendered content.
    cy.get('.accordion')
      .first()
      .invoke('text')
      .then((firstPageText) => {
        cy.get('.pagination').contains('2').click();
        cy.get('.accordion').first().invoke('text').should('not.eq', firstPageText);
      });
  });
});
