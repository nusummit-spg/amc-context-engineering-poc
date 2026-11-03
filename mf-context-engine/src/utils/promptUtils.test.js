import test from "node:test";
import assert from "node:assert/strict";
import { getPromptText, copyTextToClipboard } from "./promptUtils.js";

test("getPromptText extracts string correctly", () => {
  assert.equal(getPromptText("What is the NAV of liquid fund?"), "What is the NAV of liquid fund?");
  assert.equal(getPromptText(""), "");
  assert.equal(getPromptText(null), "");
  assert.equal(getPromptText(undefined), "");
});

test("getPromptText extracts text or query from object structures", () => {
  assert.equal(getPromptText({ text: "Sample prompt text" }), "Sample prompt text");
  assert.equal(getPromptText({ query: "What are SEBI limits?" }), "What are SEBI limits?");
  assert.equal(getPromptText({ other: 123 }), JSON.stringify({ other: 123 }));
});

test("copyTextToClipboard handles empty or missing text safely", async () => {
  const resultEmpty = await copyTextToClipboard("");
  assert.equal(resultEmpty, false);

  const resultNull = await copyTextToClipboard(null);
  assert.equal(resultNull, false);
});

test("copyTextToClipboard works with navigator.clipboard when available", async () => {
  let copiedText = "";
  const originalClipboard = globalThis.navigator?.clipboard;

  Object.defineProperty(globalThis.navigator, "clipboard", {
    value: {
      writeText: async (text) => {
        copiedText = text;
      },
    },
    configurable: true,
    writable: true,
  });

  const result = await copyTextToClipboard("Test prompt to copy");
  assert.equal(result, true);
  assert.equal(copiedText, "Test prompt to copy");

  if (originalClipboard !== undefined) {
    Object.defineProperty(globalThis.navigator, "clipboard", {
      value: originalClipboard,
      configurable: true,
      writable: true,
    });
  } else {
    delete globalThis.navigator.clipboard;
  }
});
