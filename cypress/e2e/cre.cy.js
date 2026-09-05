describe('OpenCRE CRE page', () => {
  // Owned by scripts/seed_e2e_fixtures.py: linked to ASVS/V13.2.5 and NIST/AC-1.
  const creId = '558-807';

  it('surfaces a CRE when searching for its id', () => {
    cy.visit('/');
    cy.get('form#search-bar input[type="text"]').type(`${creId}{enter}`);
    cy.url().should('include', `/search/${creId}`);
    cy.contains('h1', 'Matching CREs').scrollIntoView().should('be.visible');
    // Data-bearing: the CRE result row itself renders (fails on empty DB).
    cy.get('.standard-page__links-container').should('contain.text', 'Mutually authenticate');
  });

  it('renders the CRE page with its title and id', () => {
    cy.visit(`/cre/${creId}`);
    cy.contains('h4.cre-page__heading', 'Mutually authenticate').should('be.visible');
    cy.contains('h5.cre-page__sub-heading', `ID: ${creId}`).should('be.visible');
    // Unfiltered page shows both linked standards.
    cy.get('.cre-page__links-container').should('contain.text', 'ASVS');
    cy.get('.cre-page__links-container').should('contain.text', 'NIST');
  });

  it('applies a standard filter case-insensitively', () => {
    // Lower-case filter renders the filter bar with the term.
    cy.visit(`/cre/${creId}?applyFilters=true&filters=asvs`);
    cy.contains('.cre-page__filters', 'Filtering on').should('be.visible');
    cy.contains('.cre-page__filters b', 'asvs').should('be.visible');
    // Data-bearing: the filter actually narrowed the links, not just the chrome.
    cy.get('.cre-page__links-container').should('contain.text', 'ASVS');
    cy.get('.cre-page__links-container').should('not.contain.text', 'NIST');

    // Upper-case filter still filters (case-insensitivity lives in the
    // applyFilters hook); the page renders without error either way.
    cy.visit(`/cre/${creId}?applyFilters=true&filters=ASVS`);
    cy.contains('.cre-page__filters b', 'ASVS').should('be.visible');
    cy.contains('h4.cre-page__heading', 'Mutually authenticate').should('be.visible');
    cy.get('.cre-page__links-container').should('contain.text', 'ASVS');
    cy.get('.cre-page__links-container').should('not.contain.text', 'NIST');
  });
});
