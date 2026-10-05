"""Server-rendered ``/admin/oie`` page: job health, queues, recent runs.

One self-contained HTML document (no JS, no assets) so it works behind the
same session auth as the JSON endpoints and degrades to ``curl``-able text.
Jinja autoescaping is on for ``render_template_string``, which matters because
run errors and stage details carry arbitrary exception text.
"""

from __future__ import annotations

from typing import Any, Dict, List

from flask import render_template_string

_PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<title>OIE runs</title>
<style>
body{font:14px/1.45 system-ui,sans-serif;margin:24px;color:#1b1f23}
table{border-collapse:collapse;margin:8px 0 24px}
th,td{border:1px solid #d0d7de;padding:4px 10px;text-align:left;vertical-align:top}
th{background:#f6f8fa}
.ok{color:#1a7f37}.degraded,.stale,.running{color:#9a6700}
.error,.failing,.never_ran,.abandoned{color:#cf222e}
.skipped{color:#6e7781}
code{background:#f6f8fa;padding:1px 4px;border-radius:4px}
pre{margin:0;white-space:pre-wrap;max-width:60em}
</style></head><body>
<h1>OIE scheduled runs</h1>
<p>Overall: <strong class="{{ 'ok' if health.healthy else 'error' }}">
{{ 'healthy' if health.healthy else 'attention needed' }}</strong>
&middot; checked {{ health.checked_at }}</p>

<h2>Jobs</h2>
<table><tr><th>job</th><th>every</th><th>state</th><th>last run</th><th>last success</th><th>next slot</th></tr>
{% for name, job in health.jobs.items() %}
<tr><td>{{ name }}</td><td>{{ job.interval_minutes }} min</td>
<td class="{{ job.state }}">{{ job.state }}</td>
<td>{% if job.last_run %}<a href="/admin/oie/runs/{{ job.last_run.id }}">{{ job.last_run.id }}</a>
 ({{ job.last_run.status }}){% else %}&ndash;{% endif %}</td>
<td>{{ job.last_success_at or '–' }}</td><td>{{ job.next_slot_at }}</td></tr>
{% endfor %}</table>

<h2>Queues</h2>
<table>{% for key, value in health.queues.items() %}
<tr><th>{{ key }}</th><td>{{ value }}</td></tr>{% endfor %}</table>

<h2>Recent runs</h2>
<table><tr><th>run</th><th>status</th><th>trigger</th><th>started (UTC)</th><th>seconds</th><th>stages</th><th>error</th></tr>
{% for run in runs %}
<tr><td><a href="/admin/oie/runs/{{ run.id }}">{{ run.id }}</a>{% if run.dry_run %} <em>(dry run)</em>{% endif %}
{% if run.attempts > 1 %}<br>attempt {{ run.attempts }}{% endif %}</td>
<td class="{{ run.status }}">{{ run.status }}</td><td>{{ run.trigger }}</td>
<td>{{ run.started_at }}</td><td>{{ run.duration_seconds if run.duration_seconds is not none else '–' }}</td>
<td>{% for stage in (run.summary or {}).get('stages', []) %}
<span class="{{ stage.status }}">{{ stage.name }}:{{ stage.status }}</span>{% if not loop.last %}, {% endif %}
{% endfor %}</td>
<td>{% if run.error %}<pre>{{ run.error }}</pre>{% endif %}</td></tr>
{% else %}<tr><td colspan="7">No runs recorded yet.</td></tr>{% endfor %}</table>
</body></html>
"""


def render_oie_page(health: Dict[str, Any], runs: List[Dict[str, Any]]) -> str:
    return render_template_string(_PAGE, health=health, runs=runs)
