const { defineConfig } = require('cypress');

module.exports = defineConfig({
  video: false,
  e2e: {
    baseUrl: 'http://127.0.0.1:5000',
    specPattern: 'cypress/e2e/**/*.cy.{js,jsx,ts,tsx}',
    supportFile: false,
  },
});
