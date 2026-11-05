// Setup for the jsdom component-test lane (Part of #586, PR4).
// @testing-library/react (v11) auto-cleans the DOM after each test. No
// @testing-library/jest-dom is present, so tests use core jest matchers against
// Testing Library queries rather than jest-dom matchers.
export {};
