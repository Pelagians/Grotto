const { chromium } = require('playwright');
const fs = require('fs');
const { resolveHeadlessServerConfig } = require('../shared/launch-options');

function ensureDir(path) {
  if (path) fs.mkdirSync(path, { recursive: true });
}

(async () => {
  const config = resolveHeadlessServerConfig(process.env);

  ensureDir(config.downloadsPath);
  ensureDir(config.artifactsDir);

  const browserServer = await chromium.launchServer({
    host: config.host,
    port: config.port,
    headless: config.headless,
    downloadsPath: config.downloadsPath,
    artifactsDir: config.artifactsDir,
    args: [
      '--disable-dev-shm-usage',
      ...config.extraArgs,
    ],
    ...config.browserLaunchOptions,
  });

  const endpoint = browserServer.wsEndpoint();
  console.log(JSON.stringify({
    status: 'ready',
    runtime: process.env.OPENQUAD_RUNTIME || 'browser-runtime-headless',
    endpoint,
    browserLaunchOptions: config.browserLaunchOptions,
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
