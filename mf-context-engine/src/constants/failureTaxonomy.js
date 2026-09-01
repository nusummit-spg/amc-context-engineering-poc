/**
 * Single source of truth for the 12 Failure Taxonomy categories (F01–F12).
 * Formatted with clear, intuitive labels and plain-language tooltips for both
 * technical and non-technical reviewers.
 */

export const FAILURE_TAXONOMY = [
  {
    code: "F01",
    label: "Misunderstood Question",
    tooltip:
      "Select this if the system misunderstood what you were asking, answered a different question, or missed the main intent of your query.",
  },
  {
    code: "F02",
    label: "Wrong Fund / Product Named",
    tooltip:
      "Select this if the system answered about the wrong mutual fund scheme, company, product, or plan option (e.g. confusing Direct vs Regular).",
  },
  {
    code: "F03",
    label: "Forgot Previous Context",
    tooltip:
      "Select this if the system forgot what you talked about in earlier messages or lost track of your conversation history.",
  },
  {
    code: "F04",
    label: "Missing Key Documents",
    tooltip:
      "Select this if the system failed to find or reference the main circulars, guidelines, or relevant documents needed for this topic.",
  },
  {
    code: "F05",
    label: "Outdated Information / Old Rules",
    tooltip:
      "Select this if the answer relied on an old, expired, or superseded circular rather than the latest active regulatory rule.",
  },
  {
    code: "F06",
    label: "Incorrect Citations / Sources",
    tooltip:
      "Select this if the cited document or page number is wrong, broken, or does not actually contain the stated clause.",
  },
  {
    code: "F07",
    label: "Unverified / Made-Up Claims",
    tooltip:
      "Select this if the answer mentions facts, numbers, or rules that are not supported by the referenced official source documents.",
  },
  {
    code: "F08",
    label: "Wrong Numbers or Dates",
    tooltip:
      "Select this if percentages, limits, dates, expense ratios (TER), or financial figures in the response are inaccurate.",
  },
  {
    code: "F09",
    label: "Incomplete / Missing Details",
    tooltip:
      "Select this if the answer left out important requirements, exceptions, or risks, or included too much unrelated filler.",
  },
  {
    code: "F10",
    label: "Confusing / Contradictory Logic",
    tooltip:
      "Select this if the answer contradicts itself, makes illogical leaps, or gives conflicting conclusions in different sentences.",
  },
  {
    code: "F11",
    label: "Unclear Writing / Jargon-Heavy",
    tooltip:
      "Select this if the answer is difficult to read, excessively wordy, overly complex, or uses awkward language.",
  },
  {
    code: "F12",
    label: "Compliance / Boundary Risk",
    tooltip:
      "Select this if the answer crosses regulatory boundaries, gives unauthorized financial advice, promotes products, or misses required disclaimers.",
  },
];

export const VALID_FAILURE_CODES = new Set(FAILURE_TAXONOMY.map((f) => f.code));
