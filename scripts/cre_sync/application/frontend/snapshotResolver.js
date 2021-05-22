module.exports = {
  testPathForConsistencyCheck: 'some/example.spec.tsx',

  resolveSnapshotPath: (testPath, snapshotExtension) =>
    testPath.replace(/\.spec\.([tj]sx?)/, `${snapshotExtension}.$1`),

  resolveTestPath: (snapshotFilePath, snapshotExtension) =>
    snapshotFilePath.replace(snapshotExtension, '.spec'),
};
