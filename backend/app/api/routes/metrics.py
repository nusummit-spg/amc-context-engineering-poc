# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

"""FastAPI router for retrieval & efficiency metrics, Prometheus export, and Dashboard UI."""
from typing import Optional

from fastapi import APIRouter
from fastapi.responses import HTMLResponse, PlainTextResponse

from app.core.metrics import get_metrics_store, load_persisted_metrics
from app.core.errors import get_error_tracker
from app.services.circuit_breaker import get_all_circuit_breakers

router = APIRouter(prefix="/metrics", tags=["monitoring"])


@router.get("/summary")
async def get_summary(phase: Optional[str] = None):
    """Returns summary metrics (p50/p99 latency, tokens, cache hit rate, error rate)."""
    store = get_metrics_store()
    summary = store.summary(filter_by_phase=phase if phase and phase != "all" else None)
    err_tracker = get_error_tracker()
    summary["error_metrics"] = err_tracker.summary()
    cb_registry = get_all_circuit_breakers()
    summary["circuit_breakers"] = {
        name: cb.get_metrics() for name, cb in cb_registry.items()
    }
    return summary


@router.get("/circuit-breakers")
async def get_circuit_breakers():
    """Returns status, telemetry, and alert history for all registered circuit breakers."""
    breakers = get_all_circuit_breakers()
    return {
        "total": len(breakers),
        "circuit_breakers": [
            {
                **cb.get_metrics(),
                "alerts": cb.get_alerts(limit=20),
            }
            for cb in breakers.values()
        ]
    }


@router.get("/recent")
async def get_recent(count: int = 100):
    """Returns the last N query metrics records."""
    store = get_metrics_store()
    records = [m.to_dict() for m in store.metrics[-count:]]
    if not records:
        # Fall back to persisted metrics if in-memory store is empty
        disk_records = load_persisted_metrics()
        records = disk_records[-count:]
    return records


@router.post("/reset")
async def reset_metrics():
    """Clears collected in-memory metrics (useful between benchmark phases)."""
    store = get_metrics_store()
    store.clear()
    err_tracker = get_error_tracker()
    err_tracker.clear()
    return {"status": "reset", "count": len(store.metrics)}


@router.get("/prometheus", response_class=PlainTextResponse)
async def get_prometheus_metrics():
    """Exports metrics in standard Prometheus exposition format."""
    store = get_metrics_store()
    summary = store.summary()
    err_summary = get_error_tracker().summary()

    lines = [
        "# HELP amc_queries_total Total number of processed AMC queries",
        "# TYPE amc_queries_total counter",
        f"amc_queries_total {summary['count']}",
        "# HELP amc_query_latency_p50_ms 50th percentile query latency in milliseconds",
        "# TYPE amc_query_latency_p50_ms gauge",
        f"amc_query_latency_p50_ms {summary['latency_p50_ms']}",
        "# HELP amc_query_latency_p99_ms 99th percentile query latency in milliseconds",
        "# TYPE amc_query_latency_p99_ms gauge",
        f"amc_query_latency_p99_ms {summary['latency_p99_ms']}",
        "# HELP amc_query_latency_avg_ms Average query latency in milliseconds",
        "# TYPE amc_query_latency_avg_ms gauge",
        f"amc_query_latency_avg_ms {summary['latency_avg_ms']}",
        "# HELP amc_cache_hit_rate Cache hit ratio (0.0 - 1.0)",
        "# TYPE amc_cache_hit_rate gauge",
        f"amc_cache_hit_rate {summary['cache_hit_rate']}",
        "# HELP amc_tokens_avg Average token count per query",
        "# TYPE amc_tokens_avg gauge",
        f"amc_tokens_avg {summary['token_avg']}",
        "# HELP amc_citation_accuracy_avg Average citation accuracy (0.0 - 1.0)",
        "# TYPE amc_citation_accuracy_avg gauge",
        f"amc_citation_accuracy_avg {summary['citation_accuracy_avg']}",
        "# HELP amc_hallucination_rate Hallucination detection rate (0.0 - 1.0)",
        "# TYPE amc_hallucination_rate gauge",
        f"amc_hallucination_rate {summary['hallucination_rate']}",
        "# HELP amc_http_requests_total Total HTTP requests recorded by middleware",
        "# TYPE amc_http_requests_total counter",
        f"amc_http_requests_total {err_summary['total_requests']}",
        "# HELP amc_http_errors_total Total HTTP errors recorded by status category",
        "# TYPE amc_http_errors_total counter",
        f'amc_http_errors_total{{category="4xx"}} {err_summary["errors_4xx"]}',
        f'amc_http_errors_total{{category="5xx"}} {err_summary["errors_5xx"]}',
        "# HELP amc_http_error_rate Ratio of erroneous requests (0.0 - 1.0)",
        "# TYPE amc_http_error_rate gauge",
        f"amc_http_error_rate {err_summary['error_rate']}",
    ]
    breakers = get_all_circuit_breakers()
    if breakers:
        lines.append("# HELP amc_circuit_breaker_state Current circuit breaker state (0=closed, 1=half_open, 2=open)")
        lines.append("# TYPE amc_circuit_breaker_state gauge")
        for name, cb in breakers.items():
            metrics_data = cb.get_metrics()
            lines.append(f'amc_circuit_breaker_state{{service="{name}"}} {metrics_data["state_code"]}')
        lines.append("# HELP amc_circuit_breaker_trips_total Total times circuit breaker tripped to open")
        lines.append("# TYPE amc_circuit_breaker_trips_total counter")
        for name, cb in breakers.items():
            metrics_data = cb.get_metrics()
            lines.append(f'amc_circuit_breaker_trips_total{{service="{name}"}} {metrics_data["total_trips"]}')
        lines.append("# HELP amc_circuit_breaker_failures_total Total failure attempts recorded")
        lines.append("# TYPE amc_circuit_breaker_failures_total counter")
        for name, cb in breakers.items():
            metrics_data = cb.get_metrics()
            lines.append(f'amc_circuit_breaker_failures_total{{service="{name}"}} {metrics_data["failed_calls"]}')
    return "\n".join(lines) + "\n"


@router.get("/dashboard", response_class=HTMLResponse)
async def get_dashboard():
    """Renders a self-contained, responsive AMC Platform Operational Metrics Dashboard."""
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>AMC Platform — Operational Metrics & Health</title>
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --card-border: #334155;
      --text-main: #f8fafc;
      --text-muted: #94a3b8;
      --accent: #38bdf8;
      --accent-hover: #0284c7;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --font-stack: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background-color: var(--bg);
      color: var(--text-main);
      font-family: var(--font-stack);
      padding: 24px;
      line-height: 1.5;
    }
    .header {
      display: flex;
      flex-wrap: wrap;
      justify-content: space-between;
      align-items: center;
      gap: 16px;
      margin-bottom: 24px;
      padding-bottom: 16px;
      border-bottom: 1px solid var(--card-border);
    }
    .title-group h1 {
      font-size: 1.5rem;
      font-weight: 700;
      color: #ffffff;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    .badge {
      display: inline-block;
      padding: 2px 8px;
      font-size: 0.75rem;
      font-weight: 600;
      border-radius: 9999px;
      background: #0284c7;
      color: #ffffff;
    }
    .status-pill {
      display: inline-flex;
      align-items: center;
      gap: 6px;
      padding: 4px 12px;
      border-radius: 9999px;
      font-size: 0.8rem;
      font-weight: 600;
      background: rgba(16, 185, 129, 0.15);
      color: var(--success);
      border: 1px solid rgba(16, 185, 129, 0.3);
    }
    .status-dot {
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--success);
    }
    .controls {
      display: flex;
      align-items: center;
      gap: 10px;
    }
    button, select {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      color: var(--text-main);
      padding: 8px 14px;
      border-radius: 6px;
      font-size: 0.85rem;
      cursor: pointer;
      transition: all 0.2s;
    }
    button:hover, select:hover {
      border-color: var(--accent);
    }
    .btn-primary {
      background: var(--accent);
      color: #0f172a;
      font-weight: 600;
      border: none;
    }
    .btn-primary:hover {
      background: #7dd3fc;
    }
    .grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 16px;
      margin-bottom: 24px;
    }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 16px;
      position: relative;
    }
    .card-title {
      font-size: 0.75rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.05em;
      color: var(--text-muted);
      margin-bottom: 6px;
    }
    .card-value {
      font-size: 1.8rem;
      font-weight: 700;
      color: #ffffff;
    }
    .card-sub {
      font-size: 0.75rem;
      color: var(--text-muted);
      margin-top: 4px;
    }
    .charts-row {
      display: grid;
      grid-template-columns: 2fr 1fr;
      gap: 16px;
      margin-bottom: 24px;
    }
    @media (max-width: 900px) {
      .charts-row { grid-template-columns: 1fr; }
    }
    .chart-container {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      padding: 16px;
      min-height: 240px;
    }
    .chart-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 16px;
    }
    .chart-title {
      font-size: 0.95rem;
      font-weight: 600;
    }
    .bar-chart {
      display: flex;
      align-items: flex-end;
      gap: 6px;
      height: 160px;
      padding-top: 20px;
      border-bottom: 1px solid var(--card-border);
    }
    .bar-item {
      flex: 1;
      background: var(--accent);
      border-radius: 3px 3px 0 0;
      min-width: 8px;
      position: relative;
      transition: height 0.3s;
    }
    .bar-item:hover {
      background: #7dd3fc;
    }
    .bar-tooltip {
      display: none;
      position: absolute;
      bottom: 100%;
      left: 50%;
      transform: translateX(-50%);
      background: #000;
      color: #fff;
      font-size: 0.7rem;
      padding: 2px 6px;
      border-radius: 4px;
      white-space: nowrap;
      pointer-events: none;
      margin-bottom: 4px;
    }
    .bar-item:hover .bar-tooltip {
      display: block;
    }
    .table-container {
      background: var(--card-bg);
      border: 1px solid var(--card-border);
      border-radius: 8px;
      overflow-x: auto;
    }
    table {
      width: 100%;
      border-collapse: collapse;
      font-size: 0.85rem;
      text-align: left;
    }
    th, td {
      padding: 12px 16px;
      border-bottom: 1px solid var(--card-border);
    }
    th {
      background: rgba(15, 23, 42, 0.6);
      color: var(--text-muted);
      font-weight: 600;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }
    tr:hover {
      background: rgba(255, 255, 255, 0.02);
    }
    .tag {
      display: inline-block;
      padding: 2px 6px;
      font-size: 0.7rem;
      border-radius: 4px;
      font-weight: 600;
    }
    .tag-hit { background: rgba(16, 185, 129, 0.2); color: var(--success); }
    .tag-miss { background: rgba(148, 163, 184, 0.2); color: var(--text-muted); }
    .progress-bar-bg {
      background: rgba(255, 255, 255, 0.1);
      border-radius: 9999px;
      height: 8px;
      overflow: hidden;
      margin-top: 8px;
    }
    .progress-bar-fill {
      height: 100%;
      background: var(--accent);
      border-radius: 9999px;
      transition: width 0.3s;
    }
  </style>
</head>
<body>

  <div class="header">
    <div class="title-group">
      <h1>AMC ContextGraph Platform <span class="badge">Phase 1</span></h1>
      <span class="status-pill" id="healthPill"><span class="status-dot"></span> System Operational</span>
    </div>
    <div class="controls">
      <select id="autoRefreshSelect" onchange="handleAutoRefreshChange()">
        <option value="0">Auto-refresh: Off</option>
        <option value="5" selected>Every 5s</option>
        <option value="10">Every 10s</option>
        <option value="30">Every 30s</option>
      </select>
      <button class="btn-primary" onclick="loadAllMetrics()">↻ Refresh</button>
      <button onclick="resetMetrics()">Reset</button>
      <a href="/api/metrics/prometheus" target="_blank" style="text-decoration:none;"><button>Prometheus</button></a>
    </div>
  </div>

  <!-- KPI Grid -->
  <div class="grid">
    <div class="card">
      <div class="card-title">Total Queries</div>
      <div class="card-value" id="kpiCount">0</div>
      <div class="card-sub" id="kpiRequests">0 HTTP requests</div>
    </div>
    <div class="card">
      <div class="card-title">p50 Latency</div>
      <div class="card-value" id="kpiP50">0<span style="font-size:1rem;font-weight:400;color:var(--text-muted);">ms</span></div>
      <div class="card-sub">Target &lt; 1,800ms</div>
    </div>
    <div class="card">
      <div class="card-title">p99 Latency</div>
      <div class="card-value" id="kpiP99">0<span style="font-size:1rem;font-weight:400;color:var(--text-muted);">ms</span></div>
      <div class="card-sub">Tail latency</div>
    </div>
    <div class="card">
      <div class="card-title">Cache Hit Rate</div>
      <div class="card-value" id="kpiCache">0%</div>
      <div class="progress-bar-bg"><div class="progress-bar-fill" id="kpiCacheFill" style="width:0%;"></div></div>
    </div>
    <div class="card">
      <div class="card-title">Error Rate</div>
      <div class="card-value" id="kpiErrors">0%</div>
      <div class="card-sub" id="kpiErrorCounts">0 (4xx) / 0 (5xx)</div>
    </div>
    <div class="card">
      <div class="card-title">Avg Tokens</div>
      <div class="card-value" id="kpiTokens">0</div>
      <div class="card-sub">Input + Output per query</div>
    </div>
  </div>

  <!-- Charts Row -->
  <div class="charts-row">
    <div class="chart-container">
      <div class="chart-header">
        <span class="chart-title">Recent Query Latencies (ms)</span>
        <span style="font-size:0.75rem;color:var(--text-muted);" id="recentCountLabel">0 records</span>
      </div>
      <div class="bar-chart" id="latencyBarChart">
        <div style="margin:auto;color:var(--text-muted);font-size:0.85rem;">No recent queries recorded yet</div>
      </div>
    </div>

    <div class="chart-container">
      <div class="chart-header">
        <span class="chart-title">Quality & Efficiency Gates</span>
      </div>
      <div style="display:flex;flex-direction:column;gap:16px;margin-top:12px;">
        <div>
          <div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:4px;">
            <span>Citation Accuracy</span>
            <span id="gateCitation">100%</span>
          </div>
          <div class="progress-bar-bg"><div class="progress-bar-fill" id="gateCitationFill" style="width:100%;background:var(--success);"></div></div>
        </div>
        <div>
          <div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:4px;">
            <span>Hallucination Rate</span>
            <span id="gateHallucination">0%</span>
          </div>
          <div class="progress-bar-bg"><div class="progress-bar-fill" id="gateHallucinationFill" style="width:0%;background:var(--danger);"></div></div>
        </div>
        <div>
          <div style="display:flex;justify-content:space-between;font-size:0.8rem;margin-bottom:4px;">
            <span>Average Latency</span>
            <span id="gateAvgLatency">0ms</span>
          </div>
          <div class="progress-bar-bg"><div class="progress-bar-fill" id="gateAvgFill" style="width:0%;"></div></div>
        </div>
      </div>
    </div>
  </div>

  <!-- Recent Queries Table -->
  <div class="table-container">
    <div style="padding:16px;font-weight:600;font-size:0.95rem;border-bottom:1px solid var(--card-border);">
      Recent Queries & Execution Breakdown
    </div>
    <table>
      <thead>
        <tr>
          <th>Timestamp</th>
          <th>Request ID</th>
          <th>Query</th>
          <th>Latency</th>
          <th>Cache</th>
          <th>Tokens</th>
          <th>Citations</th>
        </tr>
      </thead>
      <tbody id="queriesTableBody">
        <tr>
          <td colspan="7" style="text-align:center;color:var(--text-muted);padding:24px;">No recent query records found.</td>
        </tr>
      </tbody>
    </table>
  </div>

  <script>
    let refreshInterval = null;

    async function loadAllMetrics() {
      try {
        const [sumRes, recentRes, healthRes] = await Promise.all([
          fetch('/api/metrics/summary').then(r => r.json()).catch(() => null),
          fetch('/api/metrics/recent?count=30').then(r => r.json()).catch(() => []),
          fetch('/api/health').then(r => r.json()).catch(() => null),
        ]);

        if (healthRes) {
          const pill = document.getElementById('healthPill');
          if (healthRes.status === 'ok') {
            pill.style.color = 'var(--success)';
            pill.style.borderColor = 'rgba(16, 185, 129, 0.3)';
            pill.innerHTML = '<span class="status-dot"></span> System Operational';
          } else {
            pill.style.color = 'var(--warning)';
            pill.style.borderColor = 'rgba(245, 158, 11, 0.3)';
            pill.innerHTML = '<span class="status-dot" style="background:var(--warning);"></span> Degraded';
          }
        }

        if (sumRes) {
          document.getElementById('kpiCount').innerText = sumRes.count || 0;
          document.getElementById('kpiP50').innerHTML = `${sumRes.latency_p50_ms || 0}<span style="font-size:1rem;font-weight:400;color:var(--text-muted);">ms</span>`;
          document.getElementById('kpiP99').innerHTML = `${sumRes.latency_p99_ms || 0}<span style="font-size:1rem;font-weight:400;color:var(--text-muted);">ms</span>`;
          
          const cachePct = Math.round((sumRes.cache_hit_rate || 0) * 100);
          document.getElementById('kpiCache').innerText = `${cachePct}%`;
          document.getElementById('kpiCacheFill').style.width = `${Math.min(cachePct, 100)}%`;

          document.getElementById('kpiTokens').innerText = Math.round(sumRes.token_avg || 0);

          if (sumRes.error_metrics) {
            const errs = sumRes.error_metrics;
            document.getElementById('kpiRequests').innerText = `${errs.total_requests || 0} HTTP requests`;
            const errPct = Math.round((errs.error_rate || 0) * 1000) / 10;
            document.getElementById('kpiErrors').innerText = `${errPct}%`;
            document.getElementById('kpiErrorCounts').innerText = `${errs.errors_4xx || 0} (4xx) / ${errs.errors_5xx || 0} (5xx)`;
          }

          const citPct = Math.round((sumRes.citation_accuracy_avg || 1.0) * 100);
          document.getElementById('gateCitation').innerText = `${citPct}%`;
          document.getElementById('gateCitationFill').style.width = `${citPct}%`;

          const halPct = Math.round((sumRes.hallucination_rate || 0) * 100);
          document.getElementById('gateHallucination').innerText = `${halPct}%`;
          document.getElementById('gateHallucinationFill').style.width = `${halPct}%`;

          const avgLat = sumRes.latency_avg_ms || 0;
          document.getElementById('gateAvgLatency').innerText = `${avgLat}ms`;
          document.getElementById('gateAvgFill').style.width = `${Math.min(Math.round((avgLat / 2500) * 100), 100)}%`;
        }

        renderRecent(recentRes || []);
      } catch (err) {
        console.error('Failed to load metrics:', err);
      }
    }

    function renderRecent(records) {
      const chart = document.getElementById('latencyBarChart');
      const label = document.getElementById('recentCountLabel');
      const tbody = document.getElementById('queriesTableBody');

      label.innerText = `${records.length} records`;

      if (!records || records.length === 0) {
        chart.innerHTML = '<div style="margin:auto;color:var(--text-muted);font-size:0.85rem;">No recent queries recorded yet</div>';
        tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;color:var(--text-muted);padding:24px;">No recent query records found.</td></tr>';
        return;
      }

      // Latency Bar Chart
      const maxLat = Math.max(...records.map(r => r.total_latency_ms || 0), 500);
      chart.innerHTML = records.map(r => {
        const height = Math.max(Math.round(((r.total_latency_ms || 0) / maxLat) * 140), 6);
        const lat = Math.round(r.total_latency_ms || 0);
        return `
          <div class="bar-item" style="height:${height}px;">
            <div class="bar-tooltip">${lat}ms<br>${(r.query || '').slice(0, 30)}</div>
          </div>
        `;
      }).join('');

      // Table rows (show last 15 in reverse chronological order)
      const displayRows = [...records].reverse().slice(0, 15);
      tbody.innerHTML = displayRows.map(r => {
        const timeStr = r.timestamp ? new Date(r.timestamp).toLocaleTimeString() : '-';
        const reqId = (r.request_id || '-').slice(0, 8);
        const queryText = (r.query || '-').length > 55 ? (r.query || '').slice(0, 55) + '...' : (r.query || '-');
        const lat = `${Math.round(r.total_latency_ms || 0)}ms`;
        const cacheTag = r.cache_hit ? '<span class="tag tag-hit">HIT</span>' : '<span class="tag tag-miss">MISS</span>';
        const tokens = (r.total_input_tokens || 0) + (r.total_output_tokens || 0);
        const citations = `${Math.round((r.citation_accuracy || 1.0) * 100)}%`;

        return `
          <tr>
            <td style="color:var(--text-muted);font-family:monospace;">${timeStr}</td>
            <td style="font-family:monospace;color:var(--accent);">${reqId}</td>
            <td>${escapeHtml(queryText)}</td>
            <td style="font-weight:600;">${lat}</td>
            <td>${cacheTag}</td>
            <td>${tokens}</td>
            <td>${citations}</td>
          </tr>
        `;
      }).join('');
    }

    function escapeHtml(text) {
      const div = document.createElement('div');
      div.innerText = text;
      return div.innerHTML;
    }

    async function resetMetrics() {
      if (confirm('Are you sure you want to reset collected metrics?')) {
        await fetch('/api/metrics/reset', { method: 'POST' });
        loadAllMetrics();
      }
    }

    function handleAutoRefreshChange() {
      const sec = parseInt(document.getElementById('autoRefreshSelect').value, 10);
      if (refreshInterval) clearInterval(refreshInterval);
      if (sec > 0) {
        refreshInterval = setInterval(loadAllMetrics, sec * 1000);
      }
    }

    // Initial load and start 5s auto-refresh
    loadAllMetrics();
    handleAutoRefreshChange();
  </script>
</body>
</html>
"""
    return HTMLResponse(content=html_content)
