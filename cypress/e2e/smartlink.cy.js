describe('OpenCRE smartlink redirects', () => {
  // ASVS/V13.2.5 (owned by scripts/seed_e2e_fixtures.py) has exactly one
  // linked CRE, so this redirects directly to that CRE page.
  it('redirects a known standard section to an internal OpenCRE page', () => {
    cy.request({
      url: '/smartlink/standard/ASVS/V13.2.5',
      followRedirect: false,
    }).then((resp) => {
      expect(resp.status).to.eq(302);
      expect(resp.headers.location).to.eq('/cre/558-807');
    });
  });

  // A CWE section that is NOT in OpenCRE falls back to the external Mitre CWE
  // catalogue. Uses an unmapped id so the fallback is deterministic.
  it('redirects an unknown CWE section to the external Mitre catalogue', () => {
    cy.request({
      url: '/smartlink/standard/CWE/99999999',
      followRedirect: false,
    }).then((resp) => {
      expect(resp.status).to.eq(302);
      expect(resp.headers.location).to.eq('https://cwe.mitre.org/data/definitions/99999999.html');
    });
  });
});
