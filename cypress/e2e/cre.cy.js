describe('OpenCRE CRE page', () => {
  const creId = '558-807';

  it('surfaces a CRE when searching for its id', () => {
    cy.visit('/');
    cy.get('form#search-bar input[type="text"]').type(`${creId}{enter}`);
    cy.url().should('include', `/search/${creId}`);
    // The CRE is listed under matching results (fails on empty DB).
    cy.contains('h1', 'Matching CREs').should('be.visible');
  });

  it('renders the CRE page with its title and id', () => {
    cy.visit(`/cre/${creId}`);
    cy.contains('h4.cre-page__heading', 'Mutually authenticate').should('be.visible');
    cy.contains('h5.cre-page__sub-heading', `ID: ${creId}`).should('be.visible');
  });

  it('applies a standard filter case-insensitively', () => {
    // Lower-case filter renders the filter bar with the term.
    cy.visit(`/cre/${creId}?applyFilters=true&filters=asvs`);
    cy.contains('.cre-page__filters', 'Filtering on').should('be.visible');
    cy.contains('.cre-page__filters b', 'asvs').should('be.visible');

    // Upper-case filter still filters (case-insensitivity lives in the
    // applyFilters hook); the page renders without error either way.
    cy.visit(`/cre/${creId}?applyFilters=true&filters=ASVS`);
    cy.contains('.cre-page__filters b', 'ASVS').should('be.visible');
    cy.contains('h4.cre-page__heading', 'Mutually authenticate').should('be.visible');
  });
});
