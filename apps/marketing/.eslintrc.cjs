module.exports = {
  root: true,
  env: { browser: true, es2020: true },
  extends: [
    'eslint:recommended',
    'plugin:@typescript-eslint/recommended',
    'plugin:react-hooks/recommended',
    'plugin:react/recommended',
    'plugin:react/jsx-runtime',
  ],
  ignorePatterns: ['dist', '.eslintrc.cjs', 'vite.config.ts'],
  parser: '@typescript-eslint/parser',
  parserOptions: {
    ecmaVersion: 'latest',
    sourceType: 'module',
    ecmaFeatures: { jsx: true },
  },
  plugins: ['react-refresh', '@typescript-eslint', 'import'],
  settings: {
    react: { version: 'detect' },
  },
  rules: {
    // ===================
    // Matching Python/Ruff rules
    // ===================

    // F: Unused variables/imports (like Ruff F401, F841)
    '@typescript-eslint/no-unused-vars': [
      'error',
      {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        caughtErrorsIgnorePattern: '^_',
      },
    ],
    'no-unused-vars': 'off', // Use TS version instead

    // I: Import sorting (like Ruff isort)
    'import/order': [
      'error',
      {
        groups: ['builtin', 'external', 'internal', 'parent', 'sibling', 'index'],
        'newlines-between': 'always',
        alphabetize: { order: 'asc', caseInsensitive: true },
      },
    ],

    // N: Naming conventions (like Ruff N)
    '@typescript-eslint/naming-convention': [
      'warn',
      // camelCase for variables and functions
      { selector: 'variable', format: ['camelCase', 'UPPER_CASE', 'PascalCase'] },
      { selector: 'function', format: ['camelCase', 'PascalCase'] },
      // PascalCase for types, interfaces, classes
      { selector: 'typeLike', format: ['PascalCase'] },
      // Allow any format for properties (APIs often use snake_case)
      { selector: 'property', format: null },
    ],

    // W: Warnings (like Ruff W)
    'no-console': 'warn',
    'no-debugger': 'warn',

    // ===================
    // React-specific
    // ===================
    'react-refresh/only-export-components': ['warn', { allowConstantExport: true }],
    'react/prop-types': 'off', // Using TypeScript
    'react/display-name': 'off',

    // ===================
    // TypeScript-specific
    // ===================
    '@typescript-eslint/explicit-function-return-type': 'off',
    '@typescript-eslint/explicit-module-boundary-types': 'off',
    '@typescript-eslint/no-explicit-any': 'warn',
    '@typescript-eslint/no-non-null-assertion': 'warn',

    // ===================
    // General quality
    // ===================
    'no-var': 'error',
    'prefer-const': 'error',
    eqeqeq: ['error', 'always', { null: 'ignore' }],
    'no-fallthrough': 'error', // Match tsconfig noFallthroughCasesInSwitch
  },
};
