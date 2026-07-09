describe ('E2E setup smoke test', () => {
    it('loads the OpenCRE homepage', () => {
        cy.visit('http://localhost:9001')
        cy.get('body').should('be.visible')
    })
})