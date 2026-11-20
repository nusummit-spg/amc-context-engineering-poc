/**
 * Wave 4.0 (TDS-40 E11): pure helpers for the typed answer cards.
 *
 * The server is the source of truth for every figure. These helpers only FORMAT values that arrive in
 * `structured_result` (Indian digit grouping, units) and never compute a new number, so the table a user sees
 * is the verified result, just laid out.
 */

export const ANSWER_KINDS = ["STRUCTURED", "DOCUMENT", "MIXED", "ABSTAIN", "CLARIFY"];

/** The answer kind of an adapted response; responses from before Wave 4.0 are DOCUMENT answers. */
export function answerKindOf(r) {
  const kind = String(r?.answer_kind || "").toUpperCase();
  return ANSWER_KINDS.includes(kind) ? kind : "DOCUMENT";
}

/** "123456.785000" -> "1,23,456.78" (Indian grouping, half-even rounding to `places`), like the server's format_inr. */
export function formatInr(value, places = 2) {
  const text = String(value ?? "").trim();
  if (!/^-?\d+(\.\d+)?$/.test(text)) return text;
  const negative = text.startsWith("-");
  const [whole, frac = ""] = text.replace("-", "").split(".");
  let digits = (whole + frac.padEnd(places + 1, "0")).replace(/^0+(?=\d)/, "");
  // round half-even on the decimal string (no floating point)
  const keep = whole.length + places;
  const head = (whole + frac.padEnd(places + 1, "0")).slice(0, keep);
  const next = (whole + frac.padEnd(places + 1, "0")).slice(keep);
  const restNonZero = /[1-9]/.test(next.slice(1));
  let rounded = BigInt(head || "0");
  const firstDropped = Number(next[0] || "0");
  if (firstDropped > 5 || (firstDropped === 5 && (restNonZero || rounded % 2n === 1n))) rounded += 1n;
  digits = rounded.toString().padStart(places + 1, "0");
  const intPart = places ? digits.slice(0, -places) : digits;
  const fracPart = places ? digits.slice(-places) : "";
  let grouped = intPart;
  if (intPart.length > 3) {
    let rest = intPart.slice(0, -3);
    const groups = [];
    while (rest.length > 2) {
      groups.unshift(rest.slice(-2));
      rest = rest.slice(0, -2);
    }
    if (rest) groups.unshift(rest);
    grouped = `${groups.join(",")},${intPart.slice(-3)}`;
  }
  const out = places ? `${grouped}.${fracPart}` : grouped;
  return negative && /[1-9]/.test(out) ? `-${out}` : out;
}

const UNIT_LABEL = { INR_CRORE: "₹ Cr", INR_PER_UNIT: "₹ per unit", PERCENT: "%", COUNT: "count" };

/** Column header with its unit, e.g. "AAUM (₹ Cr)". */
export function columnHeader(column) {
  const unit = UNIT_LABEL[column?.unit];
  return unit && unit !== "count" ? `${column.label} (${unit})` : column?.label || column?.id || "";
}

/** Display text of one cell. Numbers keep their sign and units live in the header. */
export function cellText(value, column) {
  switch (column?.unit) {
    case "INR_CRORE": return formatInr(value, 2);
    case "INR_PER_UNIT": return formatInr(value, 4);
    case "PERCENT": return `${value}`;
    case "COUNT": return formatInr(value, 0);
    default: return value === null || value === undefined ? "—" : String(value);
  }
}

export function isNumericColumn(column) {
  return ["INR_CRORE", "INR_PER_UNIT", "PERCENT", "COUNT"].includes(column?.unit)
    || ["rank", "schemes", "plan_options"].includes(column?.id);
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** "2026-06-29" -> "29-Jun-2026". */
export function shortDate(iso) {
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(String(iso || ""));
  return m ? `${m[3]}-${MONTHS[Number(m[2]) - 1]}-${m[1]}` : String(iso || "");
}

/** Indian financial-year quarter of a period start date: 2026-01-01 -> "Q4 FY26". */
export function fyQuarter(iso) {
  const m = /^(\d{4})-(\d{2})/.exec(String(iso || ""));
  if (!m) return null;
  const year = Number(m[1]);
  const month = Number(m[2]);
  const fyEnd = month <= 3 ? year : year + 1;
  const q = Math.floor(((month - 4 + 12) % 12) / 3) + 1;
  return `Q${q} FY${String(fyEnd).slice(2)}`;
}

/** The as-of badge, e.g. "AAUM Q4 FY26" or "NAV 29-Jun-2026". */
export function asOfBadge(sr) {
  const asOf = sr?.as_of || {};
  if (asOf.period_start) {
    const fq = fyQuarter(asOf.period_start);
    return { text: `AAUM ${fq || asOf.aaum_period}`, title: `AAUM for ${asOf.aaum_period}` };
  }
  if (asOf.nav_date) return { text: `NAV ${shortDate(asOf.nav_date)}`, title: `NAV date ${asOf.nav_date}` };
  return null;
}

/** Filter chips: what the result was restricted to (never internal ids). */
export function filterChips(sr) {
  const f = sr?.filters_applied || {};
  const chips = [];
  if (f.amc) chips.push(`AMC: ${f.amc}`);
  if (f.limit) chips.push(`Top ${f.limit}`);
  if (f.plan) chips.push(`Plan: ${f.plan}`);
  if (f.option) chips.push(`Option: ${f.option}`);
  if (f.categories_total) chips.push(`${f.categories_total} categories in dataset`);
  return chips;
}

/** Exclusions worth telling the user about, as sentences. */
export function exclusionNotes(sr) {
  const e = sr?.exclusions || {};
  const notes = [];
  if (e.plan_options_without_aaum_for_period) {
    notes.push(`${formatInr(e.plan_options_without_aaum_for_period, 0)} plans/options have no AAUM for this period and are not counted.`);
  }
  if (e.rejected_source_rows) notes.push(`${formatInr(e.rejected_source_rows, 0)} source rows were rejected at staging.`);
  return notes;
}

/** The "How was this computed?" facts. */
export function computationFacts(sr) {
  if (!sr) return [];
  const facts = [
    ["Calculation", sr.intent],
    ["Metric", (sr.metric_ids || []).join(", ")],
    ["Dataset version", sr.dataset_version],
    ["Publication receipt", sr.receipt_id],
    ["Source rows used", sr.row_anchor_count != null ? formatInr(sr.row_anchor_count, 0) : null],
    ["Result hash", sr.result_set_hash],
  ];
  return facts.filter(([, v]) => v !== null && v !== undefined && v !== "");
}

/** The summary sentence of a server-rendered structured answer (its first paragraph). */
export function summaryLine(answerText) {
  return String(answerText || "").split(/\n\s*\n/)[0].trim();
}

/** Text to put in the composer when a clarification option is picked: the question plus the choice. */
export function clarifiedQuery(query, option) {
  const base = String(query || "").trim().replace(/[?.!]+$/, "");
  const pick = String(option || "").replace(/\s*\(code (\d+)\)\s*$/, " scheme code $1").trim();
  return base ? `${base} — ${pick}` : pick;
}

export const FEEDBACK_REASONS = [
  { value: "WRONG_NUMBER", label: "A figure is wrong" },
  { value: "WRONG_CITATION", label: "Wrong or missing source" },
  { value: "OUTDATED", label: "Out of date" },
  { value: "INCOMPLETE", label: "Incomplete" },
  { value: "NOT_RELEVANT", label: "Not what I asked" },
  { value: "OTHER", label: "Something else" },
];

export function isPilotFeedbackEnabled(env = import.meta.env) {
  return String(env?.VITE_AMC_PILOT_FEEDBACK ?? "").toLowerCase() === "true";
}

/** Streamed answers that did not reach their final frame are not answers. */
export const INCOMPLETE_TEXT = {
  stopped: "You stopped this answer. What is shown is incomplete and was not verified as a whole.",
  interrupted: "This answer was interrupted and withdrawn: the verified source changed or became unavailable. Please ask again.",
};
