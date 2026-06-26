import assert from 'node:assert/strict';
import { createRequire } from 'node:module';
import test from 'node:test';

const require = createRequire(import.meta.url);
const {
  resolveHeadlessServerConfig,
} = require('../../runtimes/browser/shared/launch-options.js');

test('resolveHeadlessServerConfig prefers generic browser endpoint aliases over legacy Playwright names', () => {
  const config = resolveHeadlessServerConfig({
    BROWSER_WS_HOST: '127.0.0.2',
    PLAYWRIGHT_WS_HOST: '0.0.0.0',
    BROWSER_WS_PORT: '4010',
    PLAYWRIGHT_WS_PORT: '3000',
    BROWSER_HEADLESS: 'false',
    PLAYWRIGHT_HEADLESS: 'true',
    BROWSER_DOWNLOAD_DIR: '/tmp/downloads',
    BROWSER_ARTIFACTS_DIR: '/tmp/artifacts',
  });

  assert.equal(config.host, '127.0.0.2');
  assert.equal(config.port, 4010);
  assert.equal(config.headless, false);
  assert.equal(config.downloadsPath, '/tmp/downloads');
  assert.equal(config.artifactsDir, '/tmp/artifacts');
});

test('resolveHeadlessServerConfig preserves legacy env names when generic aliases are absent', () => {
  const config = resolveHeadlessServerConfig({
    PLAYWRIGHT_WS_HOST: '0.0.0.0',
    PLAYWRIGHT_WS_PORT: '3000',
    PLAYWRIGHT_HEADLESS: 'false',
    CHROMIUM_ARGS: '--disable-gpu --no-sandbox',
  });

  assert.equal(config.host, '0.0.0.0');
  assert.equal(config.port, 3000);
  assert.equal(config.headless, false);
  assert.deepEqual(config.extraArgs, ['--disable-gpu', '--no-sandbox']);
});

test('resolveHeadlessServerConfig supports Playwright channel selection for branded browsers', () => {
  const config = resolveHeadlessServerConfig({
    PLAYWRIGHT_BROWSER_CHANNEL: 'chrome',
  });

  assert.deepEqual(config.browserLaunchOptions, { channel: 'chrome' });
});

test('resolveHeadlessServerConfig lets explicit browser executable path override channel selection', () => {
  const config = resolveHeadlessServerConfig({
    PLAYWRIGHT_BROWSER_CHANNEL: 'chrome',
    BROWSER_EXECUTABLE_PATH: '/usr/bin/brave-browser',
  });

  assert.deepEqual(config.browserLaunchOptions, { executablePath: '/usr/bin/brave-browser' });
});

test('resolveHeadlessServerConfig combines generic and legacy browser extra args', () => {
  const config = resolveHeadlessServerConfig({
    CHROMIUM_ARGS: '--legacy-a --legacy-b',
    BROWSER_EXTRA_ARGS: '--generic-a --generic-b',
  });

  assert.deepEqual(config.extraArgs, [
    '--legacy-a',
    '--legacy-b',
    '--generic-a',
    '--generic-b',
  ]);
});
