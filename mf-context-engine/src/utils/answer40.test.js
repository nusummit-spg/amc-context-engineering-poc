import { test } from "node:test";
import assert from "node:assert/strict";
import {
  answerKindOf, asOfBadge, cellText, clarifiedQuery, columnHeader, computationFacts, exclusionNotes, filterChips,
  formatInr, fyQuarter, isPilotFeedbackEnabled, shortDate, summaryLine,
} from "./answer40.js";
import { PILOT_W40_API, isPilotApiAllowed } from "./pilotSources.js";

test("formatInr groups the Indian way and rounds half-even on the decimal string", () => {
  assert.equal(formatInr("1260906.025900"), "12,60,906.03");
  assert.equal(formatInr("123456.785000"), "1,23,456.78");     // half-even: 8 stays
  assert.equal(formatInr("123456.775000"), "1,23,456.78");     // half-even: 7 rounds up to 8
  assert.equal(formatInr("0.005"), "0.00");
  assert.equal(formatInr("999.995"), "1,000.00");
  assert.equal(formatInr("922.670000", 4), "922.6700");
  assert.equal(formatInr("16245", 0), "16,245");
  assert.equal(formatInr("-1234567.5", 0), "-12,34,568");
  assert.equal(formatInr("n/a"), "n/a");                        // never invents a number
});

test("cells format by unit and headers carry the unit", () => {
  assert.equal(cellText("952359.702600", { unit: "INR_CRORE" }), "9,52,359.70");
  assert.equal(cellText("61.511600", { unit: "INR_PER_UNIT" }), "61.5116");
  assert.equal(cellText("15.22", { unit: "PERCENT" }), "15.22");
  assert.equal(cellText(3678, { unit: "COUNT" }), "3,678");
  assert.equal(cellText(null, {}), "—");
  assert.equal(columnHeader({ label: "AAUM", unit: "INR_CRORE" }), "AAUM (₹ Cr)");
  assert.equal(columnHeader({ label: "Schemes", unit: "COUNT" }), "Schemes");
});

test("as-of badge uses the Indian financial-year quarter or the NAV date", () => {
  assert.equal(fyQuarter("2026-01-01"), "Q4 FY26");
  assert.equal(fyQuarter("2025-04-01"), "Q1 FY26");
  assert.equal(shortDate("2026-06-29"), "29-Jun-2026");
  assert.deepEqual(asOfBadge({ as_of: { aaum_period: "January - March 2026", period_start: "2026-01-01" } }),
    { text: "AAUM Q4 FY26", title: "AAUM for January - March 2026" });
  assert.equal(asOfBadge({ as_of: { nav_date: "2026-06-29" } }).text, "NAV 29-Jun-2026");
  assert.equal(asOfBadge({}), null);
});

test("chips, exclusions and the computation drawer show facts, never internal ids", () => {
  const sr = {
    intent: "TOP_SCHEME_AAUM", metric_ids: ["scheme_aaum_cr"], dataset_version: "fin-1", receipt_id: "r-1",
    row_anchor_count: 1234, result_set_hash: "sha256:ab",
    filters_applied: { amc: "SBI Funds Management Limited", limit: 5, plan_option_id: "secret-id" },
    exclusions: { plan_options_without_aaum_for_period: 12, rejected_source_rows: 0 },
  };
  assert.deepEqual(filterChips(sr), ["AMC: SBI Funds Management Limited", "Top 5"]);
  assert.deepEqual(exclusionNotes(sr), ["12 plans/options have no AAUM for this period and are not counted."]);
  const facts = Object.fromEntries(computationFacts(sr));
  assert.equal(facts["Source rows used"], "1,234");
  assert.equal(facts["Dataset version"], "fin-1");
});

test("answer kinds, summary and clarification text", () => {
  assert.equal(answerKindOf({ answer_kind: "structured" }), "STRUCTURED");
  assert.equal(answerKindOf({}), "DOCUMENT");                   // pre-Wave-4 answers
  assert.equal(answerKindOf({ answer_kind: "bogus" }), "DOCUMENT");
  assert.equal(summaryLine("**SBI** leads.\n\n| table |"), "**SBI** leads.");
  assert.equal(clarifiedQuery("Top 5 AMCs by AAUM in Q1 2026?", "January to March 2026 (calendar Q1 2026)"),
    "Top 5 AMCs by AAUM in Q1 2026 — January to March 2026 (calendar Q1 2026)");
  assert.equal(clarifiedQuery("NAV of the liquid fund", "X Liquid Fund - Direct - Growth (code 123456)"),
    "NAV of the liquid fund — X Liquid Fund - Direct - Growth scheme code 123456");
});

test("pilot feedback is off unless the build enables it", () => {
  assert.equal(isPilotFeedbackEnabled({}), false);
  assert.equal(isPilotFeedbackEnabled({ VITE_AMC_PILOT_FEEDBACK: "true" }), true);
});

test("the Wave 4.0 routes are admitted by the client allowlist and nothing near them is", () => {
  for (const entry of PILOT_W40_API) {
    const [method, path] = entry.split(" ");
    assert.ok(isPilotApiAllowed(method, path), entry);
  }
  assert.equal(isPilotApiAllowed("GET", "/api/feedback/v40"), false);
  assert.equal(isPilotApiAllowed("POST", "/api/ready"), false);
  assert.equal(isPilotApiAllowed("POST", "/api/feedback"), false);
});
