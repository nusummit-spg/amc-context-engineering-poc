import test from "node:test";
import assert from "node:assert/strict";
import {
  isPilotMode,
  isRawSourceUrl,
  pilotSafeSourceUrl,
} from "./pilotSources.js";

test("isPilotMode is off unless the build flag is exactly true", () => {
  assert.equal(isPilotMode({}), false);
  assert.equal(isPilotMode(undefined), false);
  assert.equal(isPilotMode({ VITE_AMC_PILOT_MODE: "false" }), false);
  assert.equal(isPilotMode({ VITE_AMC_PILOT_MODE: "1" }), false);
  assert.equal(isPilotMode({ VITE_AMC_PILOT_MODE: "true" }), true);
  assert.equal(isPilotMode({ VITE_AMC_PILOT_MODE: "TRUE" }), true);
});

test("raw document routes are recognised, including encoded and absolute forms", () => {
  for (const url of [
    "/api/files/Report.pdf",
    "/api/files/Report.pdf#page=3",
    "/api/files/data.csv?download=true",
    "/files/Report.pdf",
    "/api/docs",
    "/api/docs/DOC-001",
    "/API/FILES/Report.pdf",
    "https://app.example.org/api/files/Report.pdf",
    "/api/%66iles/Report.pdf",
  ]) {
    assert.equal(isRawSourceUrl(url), true, url);
  }
});

test("other URLs are not treated as raw document routes", () => {
  for (const url of [
    "https://www.sebi.gov.in/legal/circulars/x.html",
    "/api/query",
    "/api/filesystem/status",
    "/files-archive/x",
    "",
    null,
    undefined,
  ]) {
    assert.equal(isRawSourceUrl(url), false, String(url));
  }
});

test("pilot mode drops raw document links and keeps external ones", () => {
  assert.equal(pilotSafeSourceUrl("/api/files/A.pdf#page=2", true), null);
  assert.equal(pilotSafeSourceUrl("https://www.sebi.gov.in/x.html", true), "https://www.sebi.gov.in/x.html");
  assert.equal(pilotSafeSourceUrl(null, true), null);
});

test("non-pilot mode returns every URL unchanged", () => {
  assert.equal(pilotSafeSourceUrl("/api/files/A.pdf", false), "/api/files/A.pdf");
  assert.equal(pilotSafeSourceUrl("/files/A.pdf", false), "/files/A.pdf");
});

test("the default flag lookup tolerates a missing import.meta.env under node", () => {
  assert.equal(pilotSafeSourceUrl("/api/files/A.pdf"), "/api/files/A.pdf");
});
