#!/usr/bin/env python3
"""Rewrite the exhaustive-reingest canvas from tmp/oie_exhaustive/status.json."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATUS = ROOT / "tmp" / "oie_exhaustive" / "status.json"
CANVAS = (
    Path.home()
    / ".cursor"
    / "projects"
    / "Users-sg-Projects-OpenCRE"
    / "canvases"
    / "oie-exhaustive-reingest.canvas.tsx"
)


def main() -> int:
    if not STATUS.is_file():
        print(f"missing {STATUS}", file=sys.stderr)
        return 1
    s = json.loads(STATUS.read_text(encoding="utf-8"))
    total = int(s.get("total_targets") or 0)
    done = int(s.get("done") or 0)
    pct = (100.0 * done / total) if total else 0.0
    failures = s.get("failures") or []
    fail_rows = [
        [
            str(f.get("repo_id") or ""),
            str(f.get("status") or ""),
            str(f.get("attempts") or 0),
            (str(f.get("error") or f.get("skip_reason") or ""))[:80],
        ]
        for f in failures[:25]
    ]
    score = s.get("score") if isinstance(s.get("score"), dict) else {}
    compare = (
        score.get("compare_golden_mac_admin")
        if isinstance(score.get("compare_golden_mac_admin"), dict)
        else {}
    )

    snap = {
        "asOfUtc": s.get("as_of_utc") or "",
        "runId": s.get("run_id") or "",
        "phase": s.get("phase") or "",
        "done": done,
        "total": total,
        "pct": round(pct, 1),
        "skipped": int(s.get("skipped") or 0),
        "succeeded": int(s.get("succeeded") or 0),
        "exhausted": int(s.get("exhausted") or 0),
        "inProgress": s.get("in_progress") or "",
        "attempts": int(s.get("attempts_on_current") or 0),
        "queued": int(s.get("queue_queued") or 0),
        "started": int(s.get("queue_started") or 0),
        "etaUtc": s.get("eta_utc") or "",
        "etaNote": s.get("eta_note") or "",
        "note": s.get("note") or "",
        "failRows": fail_rows,
        "oursExact": compare.get("ours_exact"),
        "oursD1": compare.get("ours_d1"),
        "goldenExact": compare.get("golden_exact"),
        "goldenD1": compare.get("golden_d1"),
    }
    snap_json = json.dumps(snap, indent=2)

    clean = f"""import {{
  Callout, Card, CardBody, CardHeader, Grid, H1, H2, Pill, Row, Stack,
  Stat, Table, Text, UsageBar,
}} from "cursor/canvas";

const SNAP = {snap_json} as const;

function pct(v: number | null | undefined): string {{
  if (v === null || v === undefined) return "—";
  return (100 * v).toFixed(1) + "%";
}}

export default function OieExhaustiveReingest() {{
  const phaseActive = SNAP.phase !== "done";
  const failTone = SNAP.exhausted > 0 ? ("danger" as const) : ("success" as const);
  return (
    <Stack gap={{20}}>
      <Stack gap={{6}}>
        <Row gap={{10}} align="center" justify="space-between">
          <H1>OIE exhaustive incremental reingest</H1>
          <Pill active={{phaseActive}}>{{SNAP.phase}}</Pill>
        </Row>
        <Text tone="secondary" size="small">
          {{SNAP.runId}} · snapshot {{SNAP.asOfUtc}} · refresh 30m · RQ · no TRUNCATE
        </Text>
      </Stack>

      <UsageBar
        total={{Math.max(SNAP.total, 1)}}
        topLeftLabel="targets complete"
        topRightLabel={{SNAP.done + " / " + SNAP.total + " (" + SNAP.pct + "%)"}}
        segments={{[{{ id: "done", value: SNAP.done, color: "green" }}]}}
      />

      <Grid columns={{4}} gap={{12}}>
        <Stat value={{String(SNAP.succeeded)}} label="succeeded" />
        <Stat value={{String(SNAP.skipped)}} label="skipped" />
        <Stat value={{String(SNAP.exhausted)}} label="exhausted" tone={{failTone}} />
        <Stat
          value={{SNAP.etaUtc || SNAP.etaNote || "—"}}
          label={{SNAP.etaNote || "ETA"}}
        />
      </Grid>

      <Grid columns={{3}} gap={{12}}>
        <Stat value={{String(SNAP.queued)}} label="RQ queued" />
        <Stat value={{String(SNAP.started)}} label="RQ started" />
        <Stat
          value={{SNAP.inProgress || "—"}}
          label={{SNAP.attempts ? ("in progress (try " + SNAP.attempts + ")") : "in progress"}}
        />
      </Grid>

      <H2>Score vs golden_mac_admin</H2>
      <Grid columns={{4}} gap={{12}}>
        <Stat value={{pct(SNAP.oursExact)}} label="ours exact" />
        <Stat value={{pct(SNAP.oursD1)}} label="ours d1" />
        <Stat value={{pct(SNAP.goldenExact)}} label="golden exact" />
        <Stat value={{pct(SNAP.goldenD1)}} label="golden d1" />
      </Grid>

      {{SNAP.failRows.length > 0 ? (
        <Card>
          <CardHeader>Failures (exhausted / failed)</CardHeader>
          <CardBody>
            <Table
              headers={{["repo", "status", "attempts", "error"]}}
              rows={{SNAP.failRows.map((r) => [...r])}}
            />
          </CardBody>
        </Card>
      ) : (
        <Callout tone="success" title="Failure report empty">
          No exhausted targets yet.
        </Callout>
      )}}

      {{SNAP.note ? (
        <Callout tone="neutral" title="Status">
          {{SNAP.note}}
        </Callout>
      ) : null}}
    </Stack>
  );
}}
"""
    CANVAS.parent.mkdir(parents=True, exist_ok=True)
    CANVAS.write_text(clean, encoding="utf-8")
    print(f"wrote {CANVAS}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
