"""Renders a SchemaDiff scan + recommendation into a self-contained HTML
report — EP-14.1.

The report never includes a database connection string or credentials —
callers pass a `database_label` (e.g. a masked host like
`ep-cool-lake-...neon.tech`) purely for display, never the DSN itself.
See docs/dbtools/04-safety.md.
"""

from __future__ import annotations

import html
from datetime import UTC, datetime

from app.dbtools.models import EnumDiff, SchemaSnapshot, TableDiff
from app.dbtools.recommend import Recommendation, RevisionScan

_STYLE = """
:root {
  --bg: #0b1210; --panel: #101a17; --border: rgba(226,232,228,0.12);
  --tx: #eef4f1; --tx-muted: #9fb0a9; --teal: #2dd4a7; --teal-dim: rgba(45,212,167,0.14);
  --amber: #f0b74a; --amber-dim: rgba(240,183,74,0.14);
  --danger: #ef7166; --danger-dim: rgba(239,113,102,0.14);
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
}
@media (prefers-color-scheme: light) {
  :root:not([data-theme="dark"]) {
    --bg: #f6f5f0; --panel: #ffffff; --border: rgba(20,30,26,0.12);
    --tx: #14201c; --tx-muted: #52645c; --teal: #0d7d63; --teal-dim: rgba(13,125,99,0.10);
    --amber: #a06a11; --amber-dim: rgba(160,106,17,0.10);
    --danger: #b23a2f; --danger-dim: rgba(178,58,47,0.10);
  }
}
:root[data-theme="light"] {
  --bg: #f6f5f0; --panel: #ffffff; --border: rgba(20,30,26,0.12);
  --tx: #14201c; --tx-muted: #52645c; --teal: #0d7d63; --teal-dim: rgba(13,125,99,0.10);
  --amber: #a06a11; --amber-dim: rgba(160,106,17,0.10);
  --danger: #b23a2f; --danger-dim: rgba(178,58,47,0.10);
}
* { box-sizing: border-box; }
body {
  margin: 0; background: var(--bg); color: var(--tx);
  font-family: -apple-system, "Inter", system-ui, sans-serif;
  font-size: 15px; line-height: 1.55; padding: 0 0 4rem;
}
.wrap { max-width: 960px; margin: 0 auto; padding: 0 1.5rem; }
header { padding: 2.5rem 0 1.5rem; border-bottom: 1px solid var(--border); }
h1 { font-size: 1.7rem; margin: 0 0 0.5rem; }
.meta { color: var(--tx-muted); font-size: 0.85rem; }
.meta code { font-family: var(--mono); }
section { padding: 2rem 0; border-bottom: 1px solid var(--border); }
h2 { font-size: 1.15rem; margin: 0 0 1rem; }
.panel {
  border-radius: 10px; padding: 1.25rem 1.5rem; border: 1px solid var(--border);
}
.panel.ok { background: var(--teal-dim); border-color: var(--teal); }
.panel.warn { background: var(--amber-dim); border-color: var(--amber); }
.badge {
  display: inline-flex; align-items: center; font-size: 0.72rem; font-weight: 700;
  letter-spacing: 0.04em; text-transform: uppercase; padding: 0.2rem 0.6rem;
  border-radius: 999px; margin-bottom: 0.75rem;
}
.badge.ok { background: var(--teal); color: #06231c; }
.badge.warn { background: var(--amber); color: #2b1c00; }
code, pre {
  font-family: var(--mono); font-size: 0.85em;
}
pre {
  background: var(--panel); border: 1px solid var(--border); border-radius: 8px;
  padding: 0.9rem 1.1rem; overflow-x: auto; white-space: pre-wrap;
}
table { width: 100%; border-collapse: collapse; font-size: 0.86rem; }
th, td { text-align: left; padding: 0.5rem 0.75rem; border-bottom: 1px solid var(--border); }
th { font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.05em; color: var(--tx-muted); }
tr:last-child td { border-bottom: none; }
.pill {
  display: inline-block; font-size: 0.68rem; font-weight: 600; padding: 0.1rem 0.5rem;
  border-radius: 999px;
}
.pill.exact { background: var(--teal-dim); color: var(--teal); }
.pill.close { background: var(--amber-dim); color: var(--amber); }
.pill.far { background: var(--danger-dim); color: var(--danger); }
.pill.err { background: var(--danger-dim); color: var(--danger); }
details { margin-top: 0.5rem; }
summary { cursor: pointer; font-size: 0.85rem; color: var(--tx-muted); }
.diff-list { margin: 0.5rem 0 0; padding-left: 1.2rem; }
.diff-list li { margin-bottom: 0.25rem; font-size: 0.85rem; }
.tag-missing { color: var(--danger); }
.tag-extra { color: var(--amber); }
footer { padding-top: 2rem; color: var(--tx-muted); font-size: 0.78rem; }
"""


def _e(value: object) -> str:
    return html.escape(str(value))


def _diff_pill(mismatches: int) -> str:
    if mismatches == 0:
        return '<span class="pill exact">exact match</span>'
    if mismatches <= 3:
        return f'<span class="pill close">{mismatches} mismatch(es)</span>'
    return f'<span class="pill far">{mismatches} mismatch(es)</span>'


def _render_table_diff(td: TableDiff) -> str:
    items = []
    for c in td.missing_columns:
        items.append(f'<li class="tag-missing">missing column <code>{_e(c)}</code></li>')
    for c in td.extra_columns:
        items.append(f'<li class="tag-extra">extra column <code>{_e(c)}</code></li>')
    for i in td.missing_indexes:
        items.append(f'<li class="tag-missing">missing index <code>{_e(i)}</code></li>')
    for i in td.extra_indexes:
        items.append(f'<li class="tag-extra">extra index <code>{_e(i)}</code></li>')
    for c in td.missing_constraints:
        items.append(f'<li class="tag-missing">missing constraint <code>{_e(c)}</code></li>')
    for c in td.extra_constraints:
        items.append(f'<li class="tag-extra">extra constraint <code>{_e(c)}</code></li>')
    return f'<strong>{_e(td.table)}</strong><ul class="diff-list">{"".join(items)}</ul>'


def _render_enum_diff(ed: EnumDiff) -> str:
    items = []
    for v in ed.missing_values:
        items.append(f'<li class="tag-missing">missing value <code>{_e(v)}</code></li>')
    for v in ed.extra_values:
        items.append(f'<li class="tag-extra">extra value <code>{_e(v)}</code></li>')
    return f'<strong>{_e(ed.name)}</strong><ul class="diff-list">{"".join(items)}</ul>'


def render_report(
    *,
    database_label: str,
    live: SchemaSnapshot,
    recommendation: Recommendation,
    scans: list[RevisionScan],
) -> str:
    generated_at = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    if recommendation.exact_match is not None:
        rec_panel = f"""
        <div class="panel ok">
          <span class="badge ok">Safe to stamp</span>
          <p>{_e(recommendation.summary)}</p>
          <pre>{_e(recommendation.stamp_command)}
alembic -c migrations/alembic.ini upgrade head</pre>
          <p style="color: var(--tx-muted); font-size: 0.82rem;">
            This report only recommends these commands — it does not run them.
          </p>
        </div>"""
    else:
        steps_html = "".join(
            f'<li><p>{_e(step.description)}</p><pre>{_e(step.sql)}</pre></li>'
            for step in recommendation.repair_plan
        )
        rec_panel = f"""
        <div class="panel warn">
          <span class="badge warn">Repair plan required</span>
          <p>{_e(recommendation.summary)}</p>
          <ol class="diff-list">{steps_html}</ol>
        </div>"""

    alembic_row = (
        f"<code>{_e(live.alembic_version)}</code>"
        if live.alembic_version_table_exists and live.alembic_version
        else '<span class="tag-missing">not set / table does not exist</span>'
    )

    scan_rows = []
    for s in scans:
        if s.error is not None:
            status = '<span class="pill err">unparseable</span>'
            detail = f"<details><summary>parser error</summary><pre>{_e(s.error)}</pre></details>"
        else:
            status = _diff_pill(s.diff.total_mismatches)  # type: ignore[union-attr]
            detail = ""
            if s.diff.total_mismatches > 0:  # type: ignore[union-attr]
                parts = []
                if s.diff.missing_tables:
                    parts.append(
                        f'<li class="tag-missing">missing tables: '
                        f'{", ".join(f"<code>{_e(t)}</code>" for t in s.diff.missing_tables)}</li>'
                    )
                if s.diff.extra_tables:
                    parts.append(
                        f'<li class="tag-extra">extra tables: '
                        f'{", ".join(f"<code>{_e(t)}</code>" for t in s.diff.extra_tables)}</li>'
                    )
                if s.diff.missing_enums:
                    parts.append(
                        f'<li class="tag-missing">missing enums: '
                        f'{", ".join(f"<code>{_e(t)}</code>" for t in s.diff.missing_enums)}</li>'
                    )
                if s.diff.extra_enums:
                    parts.append(
                        f'<li class="tag-extra">extra enums: '
                        f'{", ".join(f"<code>{_e(t)}</code>" for t in s.diff.extra_enums)}</li>'
                    )
                table_bits = "".join(_render_table_diff(td) for td in s.diff.table_diffs)
                enum_bits = "".join(_render_enum_diff(ed) for ed in s.diff.enum_diffs)
                detail = (
                    "<details><summary>show diff</summary>"
                    f'<ul class="diff-list">{"".join(parts)}</ul>{table_bits}{enum_bits}'
                    "</details>"
                )
        scan_rows.append(
            f"<tr><td><code>{_e(s.info.revision)}</code></td>"
            f"<td>{_e(s.info.doc)}</td><td>{status}{detail}</td></tr>"
        )

    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Migration Recovery Report — {_e(database_label)}</title>
<style>{_STYLE}</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>EP-14.1 — Migration Recovery Report</h1>
    <p class="meta">Target: <code>{_e(database_label)}</code> &middot; Generated {_e(generated_at)}
      &middot; Read-only scan — no statement in this report was executed against the target.</p>
  </header>

  <section>
    <h2>Recommendation</h2>
    {rec_panel}
  </section>

  <section>
    <h2>Current state</h2>
    <table>
      <tr><th>alembic_version</th><td>{alembic_row}</td></tr>
      <tr><th>Tables found</th><td>{len(live.tables)}</td></tr>
      <tr><th>Enums found</th><td>{len(live.enums)}</td></tr>
    </table>
  </section>

  <section>
    <h2>Revision-by-revision scan</h2>
    <table>
      <thead><tr><th>Revision</th><th>Description</th><th>Result</th></tr></thead>
      <tbody>{"".join(scan_rows)}</tbody>
    </table>
  </section>

  <footer>
    Generated by <code>app.dbtools</code> (EP-14.1). This tool issues read-only
    queries only and never modifies the target database. See
    <code>backend/docs/dbtools/04-safety.md</code> for the enforcement details.
  </footer>
</div>
</body>
</html>
"""
