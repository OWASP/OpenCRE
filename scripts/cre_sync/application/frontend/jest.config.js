module.exports = {
  verbose: false,
  setupFiles: ['./enzyme-setup.js'],
  moduleNameMapper: {
    '\\.(css|scss)$': 'identity-obj-proxy',
  },
  testRegex: 'src/.*/.*spec\\.tsx?$',
  roots: ['./src'],
  moduleDirectories: ['node_modules', 'src'],
  snapshotResolver: './snapshotResolver.js',
};
