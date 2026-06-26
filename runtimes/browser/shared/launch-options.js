function firstEnv(env, names, defaultValue = '') {
  for (const name of names) {
    const value = env[name];
    if (value !== undefined && value !== '') return value;
  }
  return defaultValue;
}

function boolFromValue(value, defaultValue) {
  if (value === undefined || value === '') return defaultValue;
  return !['0', 'false', 'no', 'off'].includes(String(value).toLowerCase());
}

function numberFromValue(value, name) {
  const number = Number(value);
  if (!Number.isInteger(number) || number <= 0) {
    throw new Error(`${name} must be a positive integer, got ${JSON.stringify(value)}`);
  }
  return number;
}

function splitArgs(value) {
  if (!value) return [];
  return String(value)
    .split(/\s+/)
    .map((arg) => arg.trim())
    .filter(Boolean);
}

function resolveBrowserLaunchOptions(env = process.env) {
  const executablePath = firstEnv(env, ['BROWSER_EXECUTABLE_PATH', 'CHROMIUM_BIN']);
  if (executablePath) return { executablePath };

  const channel = firstEnv(env, ['PLAYWRIGHT_BROWSER_CHANNEL', 'BROWSER_CHANNEL']);
  if (channel) return { channel };

  return {};
}

function resolveHeadlessServerConfig(env = process.env) {
  const host = firstEnv(env, ['BROWSER_WS_HOST', 'PLAYWRIGHT_WS_HOST'], '0.0.0.0');
  const portRaw = firstEnv(env, ['BROWSER_WS_PORT', 'PLAYWRIGHT_WS_PORT'], '3000');
  const headlessRaw = firstEnv(env, ['BROWSER_HEADLESS', 'PLAYWRIGHT_HEADLESS'], 'true');
  const downloadsPath = firstEnv(env, ['BROWSER_DOWNLOAD_DIR'], '/home/pwuser/downloads');
  const artifactsDir = firstEnv(env, ['BROWSER_ARTIFACTS_DIR'], '/home/pwuser/artifacts');

  return {
    host,
    port: numberFromValue(portRaw, 'BROWSER_WS_PORT/PLAYWRIGHT_WS_PORT'),
    headless: boolFromValue(headlessRaw, true),
    downloadsPath,
    artifactsDir,
    extraArgs: [
      ...splitArgs(firstEnv(env, ['CHROMIUM_ARGS'])),
      ...splitArgs(firstEnv(env, ['BROWSER_EXTRA_ARGS'])),
    ],
    browserLaunchOptions: resolveBrowserLaunchOptions(env),
  };
}

module.exports = {
  boolFromValue,
  firstEnv,
  numberFromValue,
  resolveBrowserLaunchOptions,
  resolveHeadlessServerConfig,
  splitArgs,
};
