// TDS-40 E11.6: the Wave 4.0 pilot UI on Chromium, Firefox and WebKit against the local real stack.
//   AMC_PILOT40_DEMO_JSON=<state-dir>/demo.json npx playwright test -c playwright.pilot40.config.mjs
// Traces and screenshots are kept for every test as evidence (hash them with tools/amc_release when collecting).
import { defineConfig } from 'playwright/test';

export default defineConfig({
  testDir: './tests',
  testMatch: 'pilot40.spec.mjs',
  forbidOnly: true,
  workers: 1,
  retries: 0,
  timeout: 90000,
  outputDir: 'reports/pilot40-artifacts',
  use: { trace: 'on', screenshot: 'on' },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
    { name: 'webkit', use: { browserName: 'webkit' } },
  ],
  reporter: [['list'], ['junit', { outputFile: 'reports/pilot40_junit.xml' }]],
});
