# ===========================================================================
# Copyright © NuSummit Technologies Pvt Ltd. All rights reserved.
# 
# Author: NuSummit Developers
#
# ===========================================================================

import json
from pathlib import Path

# Load data
json_path = Path(r"c:\Users\Laptopadmin\Desktop\context-engineering\evaluation\results\multi_turn_comparison.json")
html_path = Path(r"c:\Users\Laptopadmin\Desktop\context-engineering\evaluation\results\multi_turn_report.html")

data = json.loads(json_path.read_text(encoding="utf-8"))

# Generate HTML
html = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Multi-Turn Query Evaluation Report</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            line-height: 1.6;
            color: #333;
            background-color: #ffffff;
            margin: 0;
            padding: 40px;
        }
        h1, h2, h3 {
            color: #2c3e50;
        }
        .summary {
            background-color: #f8f9fa;
            border-left: 5px solid #007bff;
            padding: 20px;
            margin-bottom: 40px;
            border-radius: 4px;
        }
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 40px;
            box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        }
        th, td {
            padding: 15px;
            text-align: left;
            border-bottom: 1px solid #e2e8f0;
            vertical-align: top;
        }
        th {
            background-color: #f1f5f9;
            font-weight: 600;
            color: #475569;
        }
        .turn-header {
            background-color: #e2e8f0;
            font-weight: bold;
        }
        .metric {
            display: inline-block;
            background-color: #e0f2fe;
            color: #0369a1;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 0.85em;
            margin-right: 5px;
            margin-bottom: 5px;
            font-weight: 500;
        }
        .metric.graph {
            background-color: #dcfce7;
            color: #166534;
        }
        .metric.trad {
            background-color: #fef3c7;
            color: #92400e;
        }
        .response-box {
            background: #fff;
            padding: 10px;
            border: 1px solid #e2e8f0;
            border-radius: 4px;
            white-space: pre-wrap;
            font-size: 0.9em;
            max-height: 250px;
            overflow-y: auto;
        }
    </style>
</head>
<body>

    <h1>Multi-Turn Query Evaluation Report</h1>
    
    <div class="summary">
        <h2>Executive Summary</h2>
        <p>This report evaluates a 3-turn conversational chain regarding Adani Corporate Structure across two retrieval pipelines: <strong>Traditional RAG (FAISS Vector-Only)</strong> and <strong>ContextGraph (Hybrid Neo4j + Vector)</strong>.</p>
        
        <h3>Key Findings:</h3>
        <ul>
            <li><strong>ContextGraph Precision:</strong> ContextGraph successfully utilized LLM query rewriting and keyword graph traversal. It retrieved the exact entity relationships from the Neo4j graph.</li>
            <li><strong>Performance:</strong> ContextGraph demonstrated high efficiency on targeted graph hits by isolating specific entity relationships rather than injecting massive vector chunks.</li>
        </ul>
    </div>

    <table>
        <thead>
            <tr>
                <th style="width: 20%;">Query (Turn)</th>
                <th style="width: 40%;">Traditional RAG</th>
                <th style="width: 40%;">ContextGraph</th>
            </tr>
        </thead>
        <tbody>
"""

for item in data:
    turn = item['turn']
    query = item['query']
    t_data = item['traditional']
    g_data = item['contextgraph']
    
    html += f"""
            <tr class="turn-header">
                <td colspan="3">Turn {turn}</td>
            </tr>
            <tr>
                <td><strong>{query}</strong></td>
                <td>
                    <div style="margin-bottom: 10px;">
                        <span class="metric trad">Latency: {t_data['time_ms']}ms</span>
                        <span class="metric trad">Tokens (In/Out): {t_data['tokens_in']}/{t_data['tokens_out']}</span>
                    </div>
                    <div class="response-box">{t_data['answer']}</div>
                </td>
                <td>
                    <div style="margin-bottom: 10px;">
                        <span class="metric graph">Latency: {g_data['time_ms']}ms</span>
                        <span class="metric graph">Tokens (In/Out): {g_data['tokens_in']}/{g_data['tokens_out']}</span>
                    </div>
                    <div class="response-box">{g_data['answer']}</div>
                </td>
            </tr>
    """

html += """
        </tbody>
    </table>

</body>
</html>
"""

html_path.write_text(html, encoding="utf-8")
print(f"HTML report successfully generated at: {html_path}")
