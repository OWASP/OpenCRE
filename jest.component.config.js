// Isolated jsdom component-test lane (Part of #586, PR4).
//
// This is deliberately NOT named jest.config.js: a bare `jest` (the existing
// `test:e2e` / puppeteer lane) auto-discovers jest.config.js, so using a
// distinct filename keeps that lane on its defaults. The new `test` script
// points here explicitly via `--config`.
//
// testMatch is scoped to the frontend component/hook tests and testPathIgnore
// excludes the puppeteer e2e (src/test/basic-e2e.test.ts).
module.exports = {
  testEnvironment: 'jsdom',
  rootDir: '.',
  roots: ['<rootDir>/application/frontend/src'],
  testMatch: [
    '<rootDir>/application/frontend/src/**/*.test.ts',
    '<rootDir>/application/frontend/src/**/*.test.tsx',
  ],
  testPathIgnorePatterns: ['/node_modules/', '<rootDir>/application/frontend/src/test/'],
  setupFilesAfterEnv: ['<rootDir>/application/frontend/src/setupTests.ts'],
  moduleNameMapper: {
    '\\.(scss|sass|css)$': 'identity-obj-proxy',
  },
};
