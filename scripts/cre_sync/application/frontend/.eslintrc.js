module.exports = {
  extends: ['airbnb', 'prettier'],
  env: {
    jest: true,
    browser: true,
  },
  plugins: ['prettier'],
  rules: {
    'prettier/prettier': ['error'],
    'import/no-named-as-default': ['off'],
  },
};
