"""Dependency-free renderers for the canonical campaign analysis model."""

from __future__ import annotations

import html
from pathlib import Path
from typing import Any

from .serialization import pretty_json


def render_markdown(model: dict[str, Any]) -> str:
    campaign = model["campaign"]
    lines = [
        f"# {campaign['title']}",
        "",
        f"- Campaign: `{campaign['campaign_id']}`",
        f"- Backend: `{campaign.get('backend_id') or 'unknown'}` "
        f"`{campaign.get('backend_version') or 'unknown'}`",
        f"- Runs: {campaign['result_runs']} results / {campaign['planned_runs']} planned",
        "- Run statuses: " + ", ".join(
            f"{key}={value}" for key, value in sorted(campaign["run_statuses"].items())
        ),
        "- System outcomes: " + ", ".join(
            f"{key}={value}" for key, value in sorted(campaign["system_outcomes"].items())
        ),
        "",
        "## Results by configuration and scenario",
        "",
    ]
    for group in model["groups"]:
        success = group["success"]
        rate = "unknown" if success["rate"] is None else f"{success['rate']:.1%}"
        interval = success["wilson_95"]
        ci = "" if interval is None else f" (Wilson 95% {interval[0]:.1%}–{interval[1]:.1%})"
        lines.extend(
            [
                f"### {group['system_id']} / {group['scenario_id']} / {group['configuration_id']}",
                "",
                f"- Success: {success['successes']}/{success['known_outcomes']} known outcomes ({rate}){ci}",
                f"- Runs with results: {group['result_runs']}/{group['planned_runs']}",
                "",
                "| Metric | Observed / planned | Summary | Unit |",
                "|---|---:|---|---|",
            ]
        )
        for metric_id, summary in sorted(group["metrics"].items()):
            if summary["value_type"] == "numeric":
                description = (
                    f"median {summary['median']:.4g} (Q1 {summary['q1']:.4g}, "
                    f"Q3 {summary['q3']:.4g}); mean {summary['mean']:.4g}"
                )
            elif summary["value_type"] == "boolean":
                description = f"true {summary['true_count']}/{summary['n_observed']} ({summary['true_rate']:.1%})"
            else:
                description = summary["value_type"]
            unit = ", ".join(summary["units"])
            lines.append(
                f"| `{metric_id}` | {summary['n_observed']} / {summary['n_planned']} "
                f"| {description} | {unit or '—'} |"
            )
        lines.append("")
    lines.extend(["## Limitations", ""])
    lines.extend(f"- {message}" for message in model["limitations"])
    lines.append("")
    return "\n".join(lines)


def render_html(model: dict[str, Any]) -> str:
    campaign = model["campaign"]
    esc = lambda value: html.escape(str(value), quote=True)
    rows = []
    for group in model["groups"]:
        success = group["success"]
        if success["rate"] is None:
            rate = "unknown"
        else:
            rate = f"{success['successes']}/{success['known_outcomes']} ({success['rate']:.1%})"
            if success["wilson_95"]:
                low, high = success["wilson_95"]
                rate += f"; Wilson 95% {low:.1%}–{high:.1%}"
        rows.append(
            "<tr>"
            f"<td>{esc(group['system_id'])}</td>"
            f"<td>{esc(group['scenario_id'])}</td>"
            f"<td>{esc(group['configuration_id'])}</td>"
            f"<td>{esc(rate)}</td>"
            f"<td>{group['result_runs']} / {group['planned_runs']}</td>"
            f"<td>{esc(_metric_list(group['metrics']))}</td>"
            "</tr>"
        )
    limitations = "".join(f"<li>{esc(item)}</li>" for item in model["limitations"])
    statuses = ", ".join(
        f"{key}: {value}" for key, value in sorted(campaign["run_statuses"].items())
    )
    outcomes = ", ".join(
        f"{key}: {value}" for key, value in sorted(campaign["system_outcomes"].items())
    )
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>{esc(campaign['title'])} — SimOps report</title>
<style>
:root {{ color-scheme: light dark; font: 16px/1.5 system-ui, sans-serif; }}
body {{ max-width: 1200px; margin: 2rem auto; padding: 0 1rem; }}
.summary {{ display: flex; flex-wrap: wrap; gap: 1rem; }}
.card {{ border: 1px solid #8886; border-radius: .6rem; padding: 1rem; min-width: 190px; }}
table {{ border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; }}
th, td {{ text-align: left; vertical-align: top; border-bottom: 1px solid #8886; padding: .65rem; }}
th {{ position: sticky; top: 0; background: Canvas; }}
code {{ overflow-wrap: anywhere; }}
</style></head><body>
<h1>{esc(campaign['title'])}</h1>
<p>Campaign <code>{esc(campaign['campaign_id'])}</code> · backend <code>{esc(campaign.get('backend_id') or 'unknown')}@{esc(campaign.get('backend_version') or 'unknown')}</code></p>
<div class="summary">
<div class="card"><strong>Runs</strong><br>{campaign['result_runs']} results / {campaign['planned_runs']} planned</div>
<div class="card"><strong>Run statuses</strong><br>{esc(statuses or 'none')}</div>
<div class="card"><strong>System outcomes</strong><br>{esc(outcomes or 'none')}</div>
</div>
<h2>Results by configuration and scenario</h2>
<div style="overflow-x:auto"><table><thead><tr><th>System</th><th>Scenario</th><th>Configuration</th><th>Success</th><th>Runs</th><th>Metrics</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></div>
<h2>Limitations</h2><ul>{limitations}</ul>
<p><a href="analysis.json">Canonical JSON analysis</a></p>
</body></html>
"""


def _metric_list(metrics: dict[str, Any]) -> str:
    parts = []
    for metric_id, summary in sorted(metrics.items()):
        if summary["value_type"] == "numeric":
            text = f"median {summary['median']:.4g}"
        elif summary["value_type"] == "boolean":
            text = f"true {summary['true_rate']:.1%}"
        else:
            text = summary["value_type"]
        parts.append(f"{metric_id}: {text} ({summary['n_observed']}/{summary['n_planned']})")
    return "; ".join(parts) or "no metrics"


def write_report(model: dict[str, Any], destination: str | Path) -> tuple[Path, Path, Path]:
    folder = Path(destination)
    folder.mkdir(parents=True, exist_ok=True)
    json_path = folder / "analysis.json"
    markdown_path = folder / "report.md"
    html_path = folder / "report.html"
    json_path.write_text(pretty_json(model), encoding="utf-8")
    markdown_path.write_text(render_markdown(model), encoding="utf-8")
    html_path.write_text(render_html(model), encoding="utf-8")
    return json_path, markdown_path, html_path
