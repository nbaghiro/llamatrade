// Metro config for the npm-workspace monorepo: resolve/transform workspace source packages (@llamatrade/core).
const { getDefaultConfig } = require('expo/metro-config');
const path = require('path');

const projectRoot = __dirname;
const workspaceRoot = path.resolve(projectRoot, '../..');

const config = getDefaultConfig(projectRoot);

// 1. Watch the whole monorepo so changes in packages/* trigger reloads.
config.watchFolders = [workspaceRoot];

// 2. Resolve from the app first, then hoisted root node_modules; hierarchical lookup stays ON for un-hoisted deps.
config.resolver.nodeModulesPaths = [
  path.resolve(projectRoot, 'node_modules'),
  path.resolve(workspaceRoot, 'node_modules'),
];

// 3. Respect the "exports" maps in @llamatrade/* (they point at TS source).
config.resolver.unstable_enablePackageExports = true;

module.exports = config;
