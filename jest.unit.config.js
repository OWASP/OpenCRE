module.exports = {
  preset: 'ts-jest',
  testEnvironment: 'node',
  testMatch: ['**/*.test.ts', '**/*.test.tsx'],
  // Exclude e2e tests (they need puppeteer/browser)
  testPathIgnorePatterns: ['/node_modules/', 'basic-e2e.test.ts'],
  moduleNameMapper: {
    // Mock CSS/SCSS imports
    '\\.(css|scss)$': 'identity-obj-proxy',
  },
  globals: {
    'ts-jest': {
      tsconfig: {
        jsx: 'react',
        esModuleInterop: true,
        allowSyntheticDefaultImports: true,
      },
    },
  },
};
