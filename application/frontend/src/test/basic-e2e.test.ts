/// <reference types = "cypress" /> 
describe('OpenCRE App E2E Tests', () => {
 

  beforeEach(() => {
    // Visit home page before each test
    cy.visit('/');
  });

  it('contains the welcome text', () => {
    cy.get('#SearchBar').should('exist').and('contain.text', 'Search');
  });

  it('can search for random strings', () => {
    cy.get('#SearchBar > div > input').type('asdf');
    cy.get('#SearchBar > div > button').click();
    cy.get('.content').should('contain.text', 'No results match your search term');
  });

  it('can search for "crypto" and return Nodes and CRES', () => {
    cy.get('#SearchBar > div > input').type('crypto');
    cy.get('#SearchBar > div > button').click();

    cy.get('.content').should('not.contain.text', 'No results match your search term');

    cy.get('.standard-page__links-container').should('have.length.greaterThan', 1);
    cy.get('.cre-page .standard-page__links-container').should('have.length.greaterThan', 1);
    cy.get('.cre-page div:nth-child(2) .standard-page__links-container').should('have.length.greaterThan', 1);
  });

  it('can search for a standard (ASVS) and verify page elements', () => {
    cy.visit(`/node/standard/ASVS`);

    cy.get('.content').should('exist').and('not.contain.text', 'No results match your search term');
    cy.get('.standard-page__heading').should('contain.text', 'ASVS');
    cy.get('.standard-page__links-container').should('have.length.greaterThan', 1);

    // Pagination
    cy.get('a[type="pageItem"][value="2"]').click();
    cy.get('.content').should('exist');

    // Click first section link
    cy.get('.standard-page__links-container > .title > a').first().click();
    cy.get('.content').should('exist');
    cy.url().should('contain', 'section');
    cy.get('.standard-page > span:nth-child(2)').should('contain.text', 'Reference:');

    // Check reference links
    cy.get('.section-page a[href]').first().should('have.attr', 'href').and('contain', 'https://');

    // Verify at least one CRE link
    cy.get('.cre-page__links-container > .title > a').first().should('exist');
  });

  it('can search for a CRE (558-807) and verify content', () => {
    cy.get('#SearchBar > div > input').type('558-807');
    cy.get('#SearchBar > div > button').click();

    cy.get('.content').should('not.contain.text', 'No results match your search term');
    cy.get('div.title.document-node').should(
      'contain.text',
      'Mutually authenticate application and credential service provider'
    );

    cy.get('.standard-page__links-container').should('have.length', 1);

    // Check nested accordions
    cy.get('.dropdown').click();
    cy.get(
      '.standard-page__links-container > .document-node > .document-node__link-type-container > div > .accordion'
    ).should('have.length.greaterThan', 1);
  });

  it('can filter CRE results', () => {
    cy.visit(`/cre/558-807?applyFilters=true&filters=asvs`);
    cy.get('.cre-page__links-container')
      .should('contain.text', 'ASVS')
      .and('contain.text', 'CRE')
      .and('not.contain.text', 'NIST');

    // Case-insensitive filter check
    cy.visit(`/cre/558-807?applyFilters=true&filters=ASVS`);
    cy.get('.cre-page__links-container')
      .should('contain.text', 'ASVS')
      .and('contain.text', 'CRE')
      .and('not.contain.text', 'NIST');

    cy.get('#clearFilterButton').should('contain.text', 'Clear Filters');
  });

  it('can smartlink', () => {
    cy.request(`/smartlink/standard/CWE/1002`).then((res) => {
      expect(res.redirectedToUrl).to.include('/node/standard/CWE/sectionid/1002');
    });

    cy.request(`smartlink/standard/CWE/404`).then((res) => {
      expect(res.redirectedToUrl).to.eq('https://cwe.mitre.org/data/definitions/404.html');
    });
  });
});