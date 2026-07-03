// TEMPORARY MOCK — replace the body of these two functions with the commented-out
// real fetch() calls once your backend teammate's endpoints are live.
// Keep the function names and return shape the same so nothing else changes.

import queries from '../data/queries';

function delay(ms) {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

export async function fetchTraditionalSearch(queryText) {
  await delay(900); // vector-only should be the faster of the two

  // MOCK — always returns the Adani preset's trad data regardless of input.
  return queries[0].trad;

  // REAL VERSION (uncomment once backend is ready):
  // const res = await fetch('/api/search/traditional', {
  //   method: 'POST',
  //   headers: { 'Content-Type': 'application/json' },
  //   body: JSON.stringify({ query: queryText }),
  // });
  // if (!res.ok) throw new Error(`Traditional search failed: ${res.status}`);
  // return res.json();
}

export async function fetchContextGraphSearch(queryText) {
  await delay(2200); // hybrid vector+graph+NER should visibly take longer

  // MOCK — always returns the Adani preset's cg data regardless of input.
  return queries[0].cg;

  // REAL VERSION (uncomment once backend is ready):
  // const res = await fetch('/api/search/contextgraph', {
  //   method: 'POST',
  //   headers: { 'Content-Type': 'application/json' },
  //   body: JSON.stringify({ query: queryText }),
  // });
  // if (!res.ok) throw new Error(`ContextGraph search failed: ${res.status}`);
  // return res.json();
}