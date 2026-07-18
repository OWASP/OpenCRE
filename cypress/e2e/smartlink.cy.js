describe('OpenCRE smartlink redirects', () => {
  // A standard section that exists in OpenCRE redirects to the internal page
  // for that section (directly to /cre/{id} when a single CRE is linked, or to
  // the /node/ section page otherwise).
  it('redirects a known standard section to an internal OpenCRE page', () => {
    cy.request({
      url: '/smartlink/standard/ASVS/V13.2.5',
      followRedirect: false,
    }).then((resp) => {
      expect(resp.status).to.eq(302);
      expect(resp.headers.location).to.match(/^\/(cre|node)\//);
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
