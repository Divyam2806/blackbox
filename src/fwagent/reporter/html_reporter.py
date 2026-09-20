import os
import json
from typing import List, Dict, Any, Tuple
from jinja2 import Template
from fwagent.models import Verdict, Finding, FirmwareModel, TestCase
from fwagent.reporter.charts import ChartGenerator


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Autonomous Firmware Test Report - {{ firmware_name }}</title>
    <style>
        :root {
            --bg-color: #0f172a;
            --card-bg: #1e293b;
            --text-color: #f8fafc;
            --accent-blue: #38bdf8;
            --pass-color: #22c55e;
            --fail-color: #ef4444;
            --warn-color: #f59e0b;
            --ambig-color: #a855f7;
            --border-color: #334155;
        }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background-color: var(--bg-color);
            color: var(--text-color);
            margin: 0;
            padding: 20px;
        }
        .container { max-width: 1200px; margin: 0 auto; }
        h1, h2, h3 { color: var(--text-color); }
        .header {
            background: linear-gradient(135deg, #1e293b, #0f172a);
            border: 1px solid var(--border-color);
            padding: 24px;
            border-radius: 12px;
            margin-bottom: 24px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.5);
        }
        .scoreboard {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
            gap: 16px;
            margin-bottom: 30px;
        }
        .card {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            padding: 16px;
            border-radius: 10px;
            text-align: center;
        }
        .card .number { font-size: 32px; font-weight: bold; margin-top: 8px; }
        .card.pass { border-color: var(--pass-color); color: var(--pass-color); }
        .card.fail { border-color: var(--fail-color); color: var(--fail-color); }
        .card.warn { border-color: var(--warn-color); color: var(--warn-color); }
        .card.ambig { border-color: var(--ambig-color); color: var(--ambig-color); }
        
        table {
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 30px;
            background-color: var(--card-bg);
            border-radius: 8px;
            overflow: hidden;
        }
        th, td {
            padding: 12px 16px;
            text-align: left;
            border-bottom: 1px solid var(--border-color);
        }
        th { background-color: #0f172a; color: var(--accent-blue); text-transform: uppercase; font-size: 12px; }
        
        .badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-weight: bold;
            font-size: 12px;
        }
        .badge.PASS { background-color: rgba(34, 197, 94, 0.2); color: var(--pass-color); }
        .badge.FAIL { background-color: rgba(239, 68, 68, 0.2); color: var(--fail-color); }
        .badge.WARN { background-color: rgba(245, 158, 11, 0.2); color: var(--warn-color); }
        .badge.AMBIGUOUS { background-color: rgba(168, 85, 247, 0.2); color: var(--ambig-color); }
        
        .code-box {
            background-color: #090d16;
            border: 1px solid var(--border-color);
            padding: 12px;
            border-radius: 6px;
            font-family: 'Consolas', 'Courier New', monospace;
            font-size: 13px;
            white-space: pre-wrap;
            color: #38bdf8;
            margin-top: 8px;
        }
        .chart-container {
            background-color: var(--card-bg);
            border: 1px solid var(--border-color);
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 30px;
            text-align: center;
        }
        .chart-container img { max-width: 100%; height: auto; border-radius: 8px; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>BLACKBOX FW-AGENT: Embedded Firmware Test Report</h1>
            <p><strong>Target Firmware:</strong> {{ firmware_name }} &nbsp;|&nbsp; <strong>Engine:</strong> Host-HAL SIL Hardware Simulator</p>
        </div>

        <div class="scoreboard">
            <div class="card">
                <div>TOTAL TESTS</div>
                <div class="number">{{ total_tests }}</div>
            </div>
            <div class="card pass">
                <div>PASS</div>
                <div class="number">{{ pass_count }}</div>
            </div>
            <div class="card fail">
                <div>FAIL</div>
                <div class="number">{{ fail_count }}</div>
            </div>
            <div class="card warn">
                <div>WARN</div>
                <div class="number">{{ warn_count }}</div>
            </div>
            <div class="card ambig">
                <div>AMBIGUOUS</div>
                <div class="number">{{ ambig_count }}</div>
            </div>
            <div class="card" style="border-color: #38bdf8;">
                <div style="color: #38bdf8;">RULE COVERAGE</div>
                <div class="number" style="color: #38bdf8;">{{ rule_coverage_pct }}%</div>
            </div>
            <div class="card" style="border-color: #38bdf8;">
                <div style="color: #38bdf8;">THRESHOLD COVERAGE</div>
                <div class="number" style="color: #38bdf8;">{{ threshold_coverage_pct }}%</div>
            </div>
        </div>

        <h2>High-Priority Findings & Line-Mapped Root Causes</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Severity</th>
                    <th>Title & Likely Cause</th>
                    <th>Evidence Tests & Lines</th>
                    <th>Firmware Lines</th>
                    <th>Suggested Fix</th>
                </tr>
            </thead>
            <tbody>
                {% for f in findings %}
                <tr>
                    <td><strong>{{ f.id }}</strong></td>
                    <td><span class="badge {{ f.severity.upper() }}">{{ f.severity }}</span></td>
                    <td>
                        <strong>{{ f.title }}</strong><br>
                        <small style="color: #94a3b8;">{{ f.likely_cause }}</small>
                    </td>
                    <td>
                        <strong>Tests:</strong> {{ f.evidence_tests | join(', ') }}<br>
                        <small style="color: #94a3b8;">{{ f.evidence_lines | join('<br>') }}</small>
                    </td>
                    <td><span style="background-color: rgba(56, 189, 248, 0.2); color: #38bdf8; padding: 2px 6px; border-radius: 4px; font-weight: bold;">Lines {{ f.firmware_lines | join(', ') }}</span></td>
                    <td><div class="code-box">{{ f.suggested_fix }}</div></td>
                </tr>
                {% endfor %}
            </tbody>
        </table>

        {% if chart_file %}
        <h2>Signal Timeline & Chatter Execution Chart (T08 / T13 Chatter Analysis)</h2>
        <div class="chart-container">
            <img src="{{ chart_file }}" alt="Signal Timeline & Chatter Chart">
        </div>
        {% endif %}

        <h2>Detailed Test Execution Results</h2>
        <table>
            <thead>
                <tr>
                    <th>ID</th>
                    <th>Verdict</th>
                    <th>Expected Behavior</th>
                    <th>Observed Result</th>
                    <th>Rules</th>
                </tr>
            </thead>
            <tbody>
                {% for v in verdicts %}
                <tr>
                    <td><strong>{{ v.test_id }}</strong></td>
                    <td><span class="badge {{ v.status }}">{{ v.status }}</span></td>
                    <td>{{ v.expected }}</td>
                    <td>{{ v.observed }}</td>
                    <td>{{ v.rule_ids | join(', ') }}</td>
                </tr>
                {% endfor %}
            </tbody>
        </table>
    </div>
</body>
</html>
"""


class HTMLReporter:
    """
    Generates standalone HTML reports with embedded CSS styling, coverage metrics, and chatter charts.
    """

    def __init__(self):
        self.chart_gen = ChartGenerator()

    def generate_report(
        self,
        firmware_name: str,
        verdicts: List[Verdict],
        findings: List[Finding],
        logs: List[Tuple[int, str]],
        out_dir: str,
        model: FirmwareModel = None,
        test_plan: List[TestCase] = None
    ) -> str:
        """Generate HTML report file."""
        os.makedirs(out_dir, exist_ok=True)
        chart_path = os.path.join(out_dir, "timeline_chart.png")
        self.chart_gen.generate_timeline_chart(logs, chart_path)

        total_tests = len(verdicts)
        pass_count = sum(1 for v in verdicts if v.status == "PASS")
        fail_count = sum(1 for v in verdicts if v.status == "FAIL")
        warn_count = sum(1 for v in verdicts if v.status == "WARN")
        ambig_count = sum(1 for v in verdicts if v.status == "AMBIGUOUS")

        # Calculate coverage summary
        from fwagent.evaluator.coverage import CoverageEvaluator
        cov_eval = CoverageEvaluator()
        cov_res = cov_eval.calculate_coverage(model, test_plan or [], verdicts)

        template = Template(HTML_TEMPLATE)
        html_out = template.render(
            firmware_name=firmware_name,
            total_tests=total_tests,
            pass_count=pass_count,
            fail_count=fail_count,
            warn_count=warn_count,
            ambig_count=ambig_count,
            rule_coverage_pct=cov_res.get("rule_coverage_pct", 100.0),
            threshold_coverage_pct=cov_res.get("threshold_coverage_pct", 100.0),
            findings=findings,
            verdicts=verdicts,
            chart_file="timeline_chart.png"
        )

        report_file = os.path.join(out_dir, "report.html")
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(html_out)

        return report_file

