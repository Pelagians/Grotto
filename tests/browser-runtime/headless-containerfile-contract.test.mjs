import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

const containerfile = readFileSync(new URL('../../Containerfile.browser-runtime-headless', import.meta.url), 'utf8');

test('headless runtime image preserves source-relative headless/shared module layout', () => {
  assert.match(
    containerfile,
    /COPY runtimes\/browser\/headless\/launch-server\.js \/opt\/openquad\/browser-runtime\/headless\/launch-server\.js/,
  );
  assert.match(
    containerfile,
    /COPY runtimes\/browser\/shared\/launch-options\.js \/opt\/openquad\/browser-runtime\/shared\/launch-options\.js/,
  );
  assert.match(
    containerfile,
    /CMD \["node", "\/opt\/openquad\/browser-runtime\/headless\/launch-server\.js"\]/,
  );
});
