import { ArrowDown, Minus } from "lucide-react";

/**
 * The point of the Compare tab is the verdict, not two dense cards to diff by
 * eye. This strip states the outcome in one scan: what each side returned, and
 * what it cost. Purely derived from the two payloads — no extra API calls.
 */
function pct(from, to) {
  if (!from || !to || from <= 0) return null;
  return Math.round(((from - to) / from) * 100);
}

function Row({ label, trad, ctx, delta }) {
  return (
    <div className="cg-cmp-row">
      <div className="cg-cmp-label">{label}</div>
      <div className="cg-cmp-val">{trad}</div>
      <div className="cg-cmp-val cg-cmp-val--ctx">
        {ctx}
        {delta}
      </div>
    </div>
  );
}

function Delta({ value, suffix = "" }) {
  if (value === null || value === undefined || Number.isNaN(value)) return null;
  if (value <= 0) {
    return (
      <span className="cg-cmp-delta cg-cmp-delta--flat">
        <Minus size={11} strokeWidth={2.5} />
        no saving
      </span>
    );
  }
  return (
    <span className="cg-cmp-delta">
      <ArrowDown size={11} strokeWidth={2.5} />
      {value}
      {suffix} less
    </span>
  );
}

export default function ComparisonSummary({ traditional, hybrid }) {
  if (!traditional || !hybrid) return null;

  const tradDocs = traditional.docs?.length ?? 0;
  const ctxSources = (
    hybrid.citations?.length ? hybrid.citations : (hybrid.provenance?.length ? hybrid.provenance : hybrid.docs || [])
  ).length;

  const tradTokens = traditional.total_tokens ?? 0;
  const ctxTokens = hybrid.total_tokens ?? 0;
  const tokenPct = pct(tradTokens, ctxTokens);

  const tradTime = traditional.total_time ?? 0;
  const ctxTime = hybrid.total_time ?? 0;
  const timeDelta = tradTime && ctxTime ? +(tradTime - ctxTime).toFixed(2) : null;

  return (
    <div className="cg-cmp-summary">
      <div className="cg-cmp-head">
        <div className="cg-cmp-label cg-cmp-label--head">At a glance</div>
        <div className="cg-cmp-val cg-cmp-head-title">
          <span className="cg-dot trad" />Traditional
        </div>
        <div className="cg-cmp-val cg-cmp-head-title">
          <span className="cg-dot ctx" />ContextGraph
        </div>
      </div>

      <Row
        label="What you get"
        trad={tradDocs > 0 ? `${tradDocs} document${tradDocs === 1 ? "" : "s"} to read` : "No documents"}
        ctx={
          <>
            1 written answer
            {ctxSources > 0 && <span className="cg-cmp-sub"> · {ctxSources} cited source{ctxSources === 1 ? "" : "s"}</span>}
          </>
        }
      />
      <Row
        label="Tokens used"
        trad={tradTokens.toLocaleString()}
        ctx={ctxTokens.toLocaleString()}
        delta={<Delta value={tokenPct} suffix="%" />}
      />
      <Row
        label="Time taken"
        trad={`${tradTime.toFixed(2)}s`}
        ctx={`${ctxTime.toFixed(2)}s`}
        delta={<Delta value={timeDelta} suffix="s" />}
      />
    </div>
  );
}
