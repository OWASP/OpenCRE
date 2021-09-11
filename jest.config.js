module.exports = {
  verbose: false,
  setupFiles: ['./enzyme-setup.js'],
  moduleNameMapper: {
    '\\.(css|scss)$': 'identity-obj-proxy',
  },
  testRegex: 'src/.*/.*spec\\.tsx?$',
  roots: ['./application/frontend/'],
  moduleDirectories: ['node_modules', 'src'],
  // snapshotResolver: 'application/frontend/snapshotResolver.js',
};
