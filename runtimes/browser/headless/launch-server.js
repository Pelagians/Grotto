const { chromium } = require('playwright');
const fs = require('fs');

function boolFromEnv(name, defaultValue) {
  const raw = process.env[name];
  if (raw === undefined || raw === '') return defaultValue;
  return !['0', 'false', 'no', 'off'].includes(raw.toLowerCase());
}

function ensureDir(path) {
  if (path) fs.mkdirSync(path, { recursive: true });
}

(async () => {
  const host = process.env.PLAYWRIGHT_WS_HOST || '0.0.0.0';
  const port = Number(process.env.PLAYWRIGHT_WS_PORT || '3000');
  const headless = boolFromEnv('PLAYWRIGHT_HEADLESS', true);
  const downloadsPath = process.env.BROWSER_DOWNLOAD_DIR || '/home/pwuser/downloads';
  const artifactsDir = process.env.BROWSER_ARTIFACTS_DIR || '/home/pwuser/artifacts';
  const extraArgs = (process.env.CHROMIUM_ARGS || '')
    .split(/\s+/)
    .map((arg) => arg.trim())
    .filter(Boolean);

  ensureDir(downloadsPath);
  ensureDir(artifactsDir);

  const browserServer = await chromium.launchServer({
    host,
    port,
    headless,
    downloadsPath,
    artifactsDir,
    args: [
      '--disable-dev-shm-usage',
      ...extraArgs,
    ],
  });

  const endpoint = browserServer.wsEndpoint();
  console.log(JSON.stringify({
    status: 'ready',
    runtime: process.env.OPENQUAD_RUNTIME || 'browser-runtime-headless',
    endpoint,
    warning: 'Treat this WebSocket as privileged browser-control access. Expose it only inside the cluster/network policy boundary.',
  }));

  const shutdown = async () => {
    await browserServer.close();
    process.exit(0);
  };
  process.on('SIGTERM', shutdown);
  process.on('SIGINT', shutdown);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
