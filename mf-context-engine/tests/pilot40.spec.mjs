// Wave 4.0 pilot UI qualification (TDS-40 E11.6) against the REAL local pilot stack (tests/live40/pilot_demo40.py):
// real app in enforce mode, PostgreSQL, Neo4j, signed FAISS, signed + approved fund dataset; LLM is the local stub.
// One test (stream interruption) replaces the stream RESPONSE in the browser to simulate a dropped connection;
// it says so. Everything else talks to the real backend. Missing configuration FAILS, it never skips.
import { readFileSync } from 'node:fs';
import { test as base, expect } from 'playwright/test';

// Sign in ONCE per user per browser and reuse that session: the login rate limiter (a security control under test
// elsewhere) answers 429 after a burst of logins from one address, and must not be relaxed for this suite.
const test = base.extend({
  user: ['alpha_analyst', { option: true }],
  signedIn: [async ({ browser }, use) => {
    const states = new Map();
    await use(async (user) => {
      if (!states.has(user)) {
        const ctx = await browser.newContext();
        const page = await ctx.newPage();
        await signIn(page, user);
        states.set(user, await ctx.storageState());
        await ctx.close();
      }
      return states.get(user);
    });
  }, { scope: 'worker' }],
  storageState: async ({ signedIn, user }, use) => { await use(await signedIn(user)); },
});

function demo() {
  const file = process.env.AMC_PILOT40_DEMO_JSON;
  if (!file) throw new Error('Set AMC_PILOT40_DEMO_JSON to the demo.json written by tests/live40/pilot_demo40.py');
  const info = JSON.parse(readFileSync(file, 'utf8'));
  const u = new URL(info.url);
  if (!['127.0.0.1', 'localhost'].includes(u.hostname)) throw new Error('pilot40 suite runs against a local stack only');
  return info;
}

async function signIn(page, user) {
  const info = demo();
  await page.goto(info.url, { waitUntil: 'domcontentloaded' });
  await page.locator('input[type="text"]').first().fill(user);
  await page.locator('input[type="password"]').first().fill(info.users[user]);
  await page.getByRole('checkbox', { name: /remember me/i }).check();      // token in localStorage => reusable
  await page.locator('button[type="submit"]').first().click();
  await expect(page.locator('.cg-chatgpt-query-input')).toBeVisible({ timeout: 30000 });
}

async function open(page) {
  await page.goto(demo().url, { waitUntil: 'domcontentloaded' });
  await expect(page.locator('.cg-chatgpt-query-input')).toBeVisible({ timeout: 30000 });
}

async function ask(page, question) {
  const box = page.locator('.cg-chatgpt-query-input');
  await box.fill(question);
  await box.press('Enter');
  const answer = page.locator('.cg-msg-assistant .cg-answer').last();
  await expect(answer).toBeVisible({ timeout: 60000 });
  return answer;
}

test.describe('verified pilot, tenant_alpha analyst', () => {
  test.beforeEach(async ({ page }) => { await open(page); });

  test('UC1 structured AAUM ranking renders the verified table with units, as-of badge and computation drawer', async ({ page }) => {
    const answer = await ask(page, 'Top 3 AMCs by AAUM');
    const card = answer.getByTestId('answer-structured');
    await expect(card).toBeVisible();
    await expect(card.getByRole('columnheader', { name: 'AAUM (₹ Cr)' })).toBeVisible();
    await expect(card.locator('tbody tr')).toHaveCount(3);
    await expect(card.locator('tbody tr').first()).toContainText('SBI Funds Management Limited');
    await expect(card.locator('tbody tr').first()).toContainText('12,60,906.03');
    await expect(card.getByLabel(/As of: AAUM for January - March 2026/)).toHaveText(/AAUM Q4 FY26/);
    const toggle = card.getByRole('button', { name: 'How was this computed?' });
    await expect(toggle).toHaveAttribute('aria-expanded', 'false');
    await toggle.click();
    await expect(toggle).toHaveAttribute('aria-expanded', 'true');
    await expect(card.getByText(demo().fin_dataset_version)).toBeVisible();
  });

  test('UC2 NAV lookup shows the NAV date badge and four-decimal NAV', async ({ page }) => {
    const card = (await ask(page, 'What is the NAV of scheme code 100033?')).getByTestId('answer-structured');
    await expect(card).toContainText('922.6700');
    await expect(card).toContainText('NAV 29-Jun-2026');
  });

  test('UC5 advice is declined with a typed refusal and no figures', async ({ page }) => {
    const card = (await ask(page, 'Should I buy SBI Nifty 50 ETF?')).getByTestId('answer-abstain');
    await expect(card).toHaveAttribute('data-code', 'OUT_OF_SCOPE_ADVICE');
    await expect(card.locator('table')).toHaveCount(0);
  });

  test('UC4 ambiguous quarter asks, the chosen option fills the box, and the follow-up is answered', async ({ page }) => {
    const card = (await ask(page, 'Top 5 AMCs by AAUM in Q1 2026')).getByTestId('answer-clarify');
    const chip = card.getByRole('button', { name: /January to March 2026/ });
    await chip.click();
    const box = page.locator('.cg-chatgpt-query-input');
    await expect(box).toHaveValue(/Q1 2026 — January to March 2026/);
    await expect(box).toBeFocused();
    await box.press('Enter');
    await expect(page.locator('.cg-answer').last().getByTestId('answer-structured')).toBeVisible({ timeout: 60000 });
  });

  test('UC3 document answer comes from this tenant only and keeps citations', async ({ page }) => {
    const answer = await ask(page, 'What is the exit load of the Debt Fund?');
    await expect(answer).toHaveAttribute('data-answer-kind', 'DOCUMENT');
    await expect(answer).toContainText('1 percent');
    for (const beta of ['Beta', '2 percent', '1.5 percent']) await expect(answer).not.toContainText(beta);
  });

  test('UC6 feedback: one rating per answer, recorded against the answer', async ({ page }) => {
    const answer = await ask(page, 'How many schemes are in the dataset?');
    await expect(answer.getByTestId('answer-structured')).toBeVisible();
    const bar = page.getByTestId('feedback-bar').last();
    await bar.getByRole('button', { name: 'No' }).click();
    await bar.getByLabel('What was wrong?').selectOption('INCOMPLETE');
    const posted = page.waitForResponse((r) => r.url().endsWith('/api/feedback/v40') && r.request().method() === 'POST');
    await bar.getByRole('button', { name: 'Send' }).click();
    expect((await posted).status()).toBe(202);
    await expect(page.getByTestId('feedback-done').last()).toBeVisible();
  });

  test('pilot surface: readiness shown, prompts come from the verified dataset, denied features absent', async ({ page }) => {
    await expect(page.getByTestId('readiness')).toHaveAttribute('data-ready', 'true');
    const starters = page.locator('.cg-chat-starter');
    await expect(starters.first()).toBeVisible();
    await expect(starters.first()).toContainText('AAUM');
    for (const generic of ['Adani', 'ESG', 'Australia']) await expect(page.locator('.cg-chat-starters')).not.toContainText(generic);
    await ask(page, 'Top 3 AMCs by AAUM');
    await expect(page.getByRole('button', { name: 'Ontology View' })).toHaveCount(0);
    await expect(page.locator('.cg-msg-action-btn', { hasText: /^Feedback$/ })).toHaveCount(0);
  });

  test('stream interruption is shown as withdrawn, not as an answer (simulated dropped connection)', async ({ page }) => {
    await page.route('**/api/chat/stream', (route) => route.fulfill({
      status: 200, contentType: 'text/event-stream',
      body: 'event: chunk\ndata: {"type": "answer_chunk", "text": "Partial text that must not stand as an answer"}\n\n',
    }));
    await page.locator('.cg-chatgpt-query-input').fill('What is the exit load of the Debt Fund?');
    await page.locator('.cg-chatgpt-query-input').press('Enter');
    await expect(page.getByTestId('answer-interrupted')).toBeVisible({ timeout: 30000 });
    await expect(page.locator('.cg-answer').last()).not.toContainText('Partial text');
    await expect(page.getByTestId('feedback-bar')).toHaveCount(0);
  });
});

test.describe('tenant_beta analyst', () => {
  test.use({ user: 'beta_analyst' });
  test('tenant isolation in the UI: tenant_beta cannot see tenant_alpha fund data', async ({ page }) => {
  await open(page);
  const answer = await ask(page, 'Top 3 AMCs by AAUM');
  await expect(answer.getByTestId('answer-structured')).toHaveCount(0);
  await expect(answer.getByTestId('answer-abstain')).toBeVisible();
  await expect(answer).not.toContainText('SBI Funds Management');
  });
});
