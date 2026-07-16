module.exports = function (api) {
  api.cache(true);
  // babel-preset-expo bundles the expo-router plugin (SDK 50+); no extra plugin needed.
  return {
    presets: ['babel-preset-expo'],
  };
};
