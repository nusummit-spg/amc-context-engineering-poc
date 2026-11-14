// Real staging integration; not unit mocks. Missing fixtures MUST fail, not skip.
import { defineConfig } from 'playwright/test';
export default defineConfig({
  testDir: './tests',
  testMatch: 'feedback_uat.spec.mjs',
  forbidOnly: true,
  workers: 1,
  retries: 0,
  timeout: 45000,
  use: { trace: 'retain-on-failure', screenshot: 'only-on-failure',
         storageState: process.env.AMC_UAT_STORAGE_STATE || undefined },
  projects: [
    { name: 'chromium', use: { browserName: 'chromium' } },
    { name: 'firefox', use: { browserName: 'firefox' } },
  ],
  reporter: [['list'], ['junit', { outputFile: 'reports/feedback_uat_junit.xml' }]],
});
