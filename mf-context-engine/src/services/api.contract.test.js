/**
 * FB06: real frontend API adapter contract tests (Node 22, no browser, no server).
 * These tests mock ONLY transport and exercise the *existing* repository api.js.
 * Browser UAT separately uses no mocks and requires an authenticated staging app.
 */
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  submitFeedback,
  fetchFeedback,
  fetchFeedbackStatus,
  fetchPendingFeedbackNotice,
  fetchFeedbackIssueDetail,
} from './api.js';

function reply(value, status = 200) {
  return new Response(JSON.stringify(value), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

test('FB06: feedback submission uses authenticated JSON POST contract', async (t) => {
  const sent = [];
  t.mock.method(globalThis, 'fetch', async (url, init) => {
    sent.push({ url, init });
    return reply({ feedback_id: 'fb_fixture', issue_status: 'reported' }, 201);
  });
  const payload = { response_id: 'rsp-7', session_id: 's-1', selected_categories: ['F01'], feedback_text: 'Test evidence' };
  const output = await submitFeedback(payload);
  assert.equal(output.feedback_id, 'fb_fixture');
  assert.equal(sent.length, 1);
  assert.equal(sent[0].url, '/api/feedback');
  assert.equal(sent[0].init.method, 'POST');
  assert.deepEqual(JSON.parse(sent[0].init.body), payload);
  assert.equal(sent[0].init.headers['Content-Type'], 'application/json');
});

test('FB06: response ID is URI encoded in feedback fetch', async (t) => {
  let observed;
  t.mock.method(globalThis, 'fetch', async (url) => { observed = url; return reply({ items: [] }); });
  await fetchFeedback('ab/c&d?z');
  assert.equal(observed, '/api/feedback?response_id=ab%2Fc%26d%3Fz');
});

test('FB06: tenant-scoped status parameters are URL encoded', async (t) => {
  let observed;
  t.mock.method(globalThis, 'fetch', async (url) => { observed = url; return reply({ has_existing_issue: true, status: 'under_review' }); });
  const info = await fetchFeedbackStatus({ responseId: 'r-1', query: 'a & b', sessionId: 's-1', tenantId: 't/42' });
  const query = new URL(observed, 'https://example.invalid');
  assert.equal(query.pathname, '/api/feedback/status');
  assert.equal(query.searchParams.get('tenant_id'), 't/42');
  assert.equal(query.searchParams.get('query'), 'a & b');
  assert.equal(info.status, 'under_review');
});

test('FB06: missing pending query sends no HTTP request', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new Error('must not be called'); });
  assert.equal(await fetchPendingFeedbackNotice({ query: '' }), null);
});

test('FB06: failed feedback POST must reject, not fabricate a stored receipt', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => reply({ detail: 'Unauthorized' }, 401));
  await assert.rejects(submitFeedback({ response_id: 'x' }), /API Error \(401\).*Unauthorized/);
});

test('FB06: unavailable status endpoint returns nonauthoritative unknown issue state', async (t) => {
  t.mock.method(globalThis, 'fetch', async () => { throw new Error('network unreachable'); });
  const info = await fetchFeedbackStatus({ responseId: 'z' });
  assert.deepEqual(info, { has_existing_issue: false });
});

test('FB06: issue ID is URL-encoded before detail fetch', async (t) => {
  let observed;
  t.mock.method(globalThis, 'fetch', async (url) => { observed = url; return reply({ issue_id: 'i/1' }); });
  await fetchFeedbackIssueDetail('i/1');
  assert.equal(observed, '/api/feedback/issues/i%2F1');
});
