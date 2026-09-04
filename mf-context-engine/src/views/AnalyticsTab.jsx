import { useMemo, useEffect } from "react";
import Radio from "../components/widgets/Radio";
import Alert from "../components/widgets/Alert";
import Divider from "../components/widgets/Divider";
import DataFrame from "../components/widgets/DataFrame";
import Metric from "../components/widgets/Metric";
import BarChart from "../components/widgets/BarChart";
import InteractiveGraph from "./panels/InteractiveGraph";
import { useAppState } from "../state/AppState";
import { getEntitySourceInfo, generateFullSubgraph } from "../data/mockEngine";

export default function AnalyticsTab() {
  const {
    lastHybrid,
    comparisons,
    analyticsScope,
    setAnalyticsScope,
    fullGraphData,
    loadFullGraph,
    isGraphLoading,
  } = useAppState();

  useEffect(() => {
    if (analyticsScope === "Full knowledge graph" && !fullGraphData) {
      loadFullGraph(60);
    }
  }, [analyticsScope, fullGraphData, loadFullGraph]);

  const lastQueryGraph = useMemo(() => {
    if (analyticsScope !== "Last query's graph" || !lastHybrid) return null;
    const usedEdges = lastHybrid.graph_edges_used_in_prompt || [];
    const isFallback = lastHybrid.graph_matched_by === "fallback" || usedEdges.length === 0;
    const edgesToShow = isFallback ? (lastHybrid.graph_edges || []).slice(0, 10) : usedEdges;
    const nodesToShow = Array.from(new Set(edgesToShow.flatMap((e) => [e.s, e.o])));
    const sourceInfo = getEntitySourceInfo(nodesToShow);
    return { edgesToShow, nodesToShow, isFallback, sourceInfo, matchedTexts: lastHybrid.matched_entity_texts || [] };
  }, [analyticsScope, lastHybrid]);

  const fullGraph = useMemo(() => {
    if (analyticsScope !== "Full knowledge graph") return null;
    if (fullGraphData) return fullGraphData;
    const full = generateFullSubgraph(60);
    const nodesToShow = Array.from(new Set(full.edges.flatMap((e) => [e.s, e.o])));
    const sourceInfo = getEntitySourceInfo(nodesToShow);
    return { edgesToShow: full.edges, nodesToShow, sourceInfo };
  }, [analyticsScope, fullGraphData]);

  const df = comparisons;
  const avgTrad = df.length ? df.reduce((a, c) => a + c.traditional_time, 0) / df.length : 0;
  const avgHybrid = df.length ? df.reduce((a, c) => a + c.hybrid_time, 0) / df.length : 0;
  const avgTokenDelta = df.length
    ? df.reduce((a, c) => a + (c.hybrid_tokens - c.traditional_tokens), 0) / df.length
    : 0;

  return (
    <div>
      <h3 className="stSubheader">Ontology &amp; Graph Explorer</h3>

      <Radio
        name="analytics-scope"
        options={["Last query's graph", "Full knowledge graph"]}
        value={analyticsScope}
        onChange={setAnalyticsScope}
      />

      <div style={{ marginTop: "0.8rem" }}>
        {analyticsScope === "Last query's graph" ? (
          !lastHybrid ? (
            <Alert type="info">Run a query in the Compare tab first to see its graph here.</Alert>
          ) : (
            <>
              {lastQueryGraph.isFallback && (
                <Alert type="warning">
                  No graph relationships were directly relevant to this query — the answer was grounded on
                  document search, not the graph. Showing the broader graph neighborhood below for reference
                  only, not as verification.
                </Alert>
              )}
              <InteractiveGraph
                nodes={lastQueryGraph.nodesToShow}
                edges={lastQueryGraph.edgesToShow}
                matchedTexts={lastQueryGraph.matchedTexts}
                sourceInfo={lastQueryGraph.sourceInfo}
                isFallbackGraph={lastQueryGraph.isFallback}
                note="Colored nodes matched your question directly. Click any node to see exactly which relationship(s) put it in this graph."
              />
            </>
          )
        ) : (
          <InteractiveGraph
            nodes={fullGraph.nodesToShow}
            edges={fullGraph.edgesToShow}
            matchedTexts={[]}
            sourceInfo={fullGraph.sourceInfo}
            isFallbackGraph={false}
            note="Showing up to 60 relationships from the full graph. Click any node to explore it."
          />
        )}
      </div>

      <Divider />
      <h3 className="stSubheader">Traditional vs. ContextGraph — run history</h3>

      {df.length === 0 ? (
        <Alert type="info">Run a query in the Compare tab first.</Alert>
      ) : (
        <>
          <DataFrame
            columns={["query", "traditional_time", "hybrid_time", "traditional_tokens", "hybrid_tokens"]}
            rows={df}
            showIndex
          />
          <div className="stMetricsGrid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))", marginTop: "0.5rem" }}>
            <Metric label="Avg traditional latency" value={`${avgTrad.toFixed(2)}s`} />
            <Metric
              label="Avg hybrid latency"
              value={`${avgHybrid.toFixed(2)}s`}
              delta={`${avgHybrid - avgTrad >= 0 ? "+" : ""}${(avgHybrid - avgTrad).toFixed(2)}s`}
            />
            <Metric label="Avg hybrid token delta" value={`${avgTokenDelta >= 0 ? "+" : ""}${avgTokenDelta.toFixed(0)}`} />
          </div>

          <div style={{ marginTop: "1rem" }}>
            <BarChart
              categories={df.map((c) => c.query)}
              series={[
                { name: "traditional_time", values: df.map((c) => c.traditional_time) },
                { name: "hybrid_time", values: df.map((c) => c.hybrid_time) },
              ]}
            />
          </div>
          <div style={{ marginTop: "1.5rem" }}>
            <BarChart
              categories={df.map((c) => c.query)}
              series={[
                { name: "traditional_tokens", values: df.map((c) => c.traditional_tokens) },
                { name: "hybrid_tokens", values: df.map((c) => c.hybrid_tokens) },
              ]}
            />
          </div>
        </>
      )}
    </div>
  );
}
