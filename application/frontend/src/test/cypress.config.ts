import type { Cypress } from "cypress";

const config: Cypress.ConfigOptions = {
  e2e: {
    baseUrl: "http://localhost:9001",
    setupNodeEvents(on, config) {
      // node events
    },
  },
};

export default config;