import { test, expect } from 'playwright/test';

const url = process.env.AMC_UAT_FEEDBACK_URL;
const lockedUrl = process.env.AMC_UAT_LOCKED_FEEDBACK_URL;
const allowed = process.env.AMC_UAT_ALLOWED_HOST;

function requireStaging(testUrl) {
  if (!testUrl || !allowed || !process.env.AMC_UAT_STORAGE_STATE) {
    throw new Error('Explicit staging URL, hostname allowlist, and authenticated storageState required');
  }
  const u = new URL(testUrl);
  if (u.protocol !== 'https:' || u.hostname !== allowed) {
    throw new Error('Test URL must use allowlisted HTTPS staging host');
  }
}

test('FB06: submit real feedback on current turn and see persisted receipt', async ({ page }) => {
  requireStaging(url);
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('FEEDBACK & REVIEW AUDIT')).toBeVisible();
  const field = page.getByPlaceholder('Add your comments on this answer…');
  await expect(field).toBeEnabled();
  await field.fill(`Staging UAT synthetic feedback ${Date.now()}`);
  const submit = page.locator('.cg-feedback-submit-btn');
  await expect(submit).toBeEnabled();
  // Observe real API transaction; do not intercept/mock it.
  const response = page.waitForResponse(r => r.url().includes('/api/feedback') && r.request().method() === 'POST');
  await submit.click();
  const result = await response;
  expect(result.status()).toBeGreaterThanOrEqual(200);
  expect(result.status()).toBeLessThan(300);
  await expect(page.getByText('Feedback recorded', { exact: false })).toBeVisible();
});

test('FB06: previous-turn feedback cannot be submitted', async ({ page }) => {
  requireStaging(lockedUrl);
  await page.goto(lockedUrl, { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('LOCKED · PREVIOUS TURN')).toBeVisible();
  await expect(page.locator('.cg-feedback-submit-btn')).toBeDisabled();
});

// Wave 2.4: three additional real-browser, no-network-mock acceptance cases.
test('FB06: empty feedback cannot trigger a write', async ({ page }) => {
  requireStaging(url);
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  await expect(page.getByText('FEEDBACK & REVIEW AUDIT')).toBeVisible();
  await expect(page.locator('.cg-feedback-submit-btn')).toBeDisabled();
});

test('FB06: taxonomy checkbox enables feedback and Clear all revokes eligibility', async ({ page }) => {
  requireStaging(url);
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  const taxonomy = page.getByRole('group', { name: 'Failure Taxonomy Categories' });
  const first = taxonomy.locator('input[type="checkbox"]').first();
  await expect(first).toBeEnabled();
  await first.check();
  await expect(page.locator('.cg-feedback-submit-btn')).toBeEnabled();
  await expect(page.getByText('1 issue selected')).toBeVisible();
  await page.getByRole('button', { name: 'Clear all' }).click();
  await expect(page.locator('.cg-feedback-submit-btn')).toBeDisabled();
});

test('FB06: commentary enforces the 2000-character client limit', async ({ page }) => {
  requireStaging(url);
  await page.goto(url, { waitUntil: 'domcontentloaded' });
  const field = page.getByPlaceholder('Add your comments on this answer…');
  await expect(field).toBeEnabled();
  await field.fill('a'.repeat(2001));
  await expect(field).toHaveValue('a'.repeat(2000));
});
