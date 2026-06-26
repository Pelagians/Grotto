import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const script = readFileSync(new URL('../../runtimes/browser/visible/start-visible.sh', import.meta.url), 'utf8');

test('visible runtime accepts generic browser CDP aliases while keeping Chromium legacy fallback', () => {
  assert.match(script, /BROWSER_CDP_HOST=.*CHROMIUM_CDP_HOST/s);
  assert.match(script, /BROWSER_CDP_PORT=.*CHROMIUM_CDP_PORT/s);
  assert.match(script, /CHROMIUM_CDP_HOST=.*BROWSER_CDP_HOST/s);
  assert.match(script, /CHROMIUM_CDP_PORT=.*BROWSER_CDP_PORT/s);
});

test('visible runtime accepts generic browser executable and extra argument aliases', () => {
  assert.match(script, /BROWSER_EXECUTABLE_PATH=.*CHROMIUM_BIN/s);
  assert.match(script, /BROWSER_EXTRA_ARGS/s);
  assert.match(script, /CHROMIUM_EXTRA_ARGS/s);
});

test('visible runtime readiness advertises generic browser contract fields', () => {
  assert.match(script, /browserExecutable/);
  assert.match(script, /cdp/);
  assert.match(script, /novnc/);
});
