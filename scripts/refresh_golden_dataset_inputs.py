#!/usr/bin/env python

"""Refresh the fixture inputs used by the golden dataset builder."""

import argparse
import json
import os
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_DB = REPO_ROOT / "standards_cache.sqlite"
DEFAULT_INPUTS = REPO_ROOT / "application/tests/librarian/fixtures/dataset_inputs"

CURATED_FIELDS = {
    "explicit": {"id", "asvs_section_id", "text_template", "title_hint"},
    "update": {"id", "asvs_section_id", "text", "prior_text"},
    "ambiguous": {"id", "text", "reason_code"},
    "cheatsheet_fixtures": {"id", "section", "text", "title_hint", "section_path"},
    "multilink_pins": {"name", "section_id"},
}


def load_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def standard_for(name):
    if "ASVS" in name:
        return "ASVS"
    if "CWE" in name:
        return "CWE"
    return "OTHER"


def node_from_rows(rows, identity):
    if not rows:
        return None

    node_ids = {row[0] for row in rows}
    if len(node_ids) != 1:
        raise ValueError(
            f"Duplicate database-node identity {identity}: " f"{sorted(node_ids)}"
        )

    node_id, name, section_id, section, _ = rows[0]
    return {
        "standard": standard_for(name),
        "name": name,
        "section_id": section_id,
        "section": section,
        "cre_ids": sorted({row[4] for row in rows}),
    }


def fetch_node(conn, name, section_id):
    rows = conn.execute(
        """
        SELECT n.id, n.name, n.section_id, n.section, c.external_id
        FROM node n
        JOIN cre_node_links l ON l.node = n.id
        JOIN cre c ON c.id = l.cre
        WHERE n.name = ? AND n.section_id = ?
        ORDER BY n.id, c.external_id
        """,
        (name, section_id),
    ).fetchall()
    return node_from_rows(rows, (name, section_id))


def fetch_node_by_id(conn, node_id):
    rows = conn.execute(
        """
        SELECT n.id, n.name, n.section_id, n.section, c.external_id
        FROM node n
        JOIN cre_node_links l ON l.node = n.id
        JOIN cre c ON c.id = l.cre
        WHERE n.id = ?
        ORDER BY c.external_id
        """,
        (node_id,),
    ).fetchall()
    return node_from_rows(rows, node_id)


def fetch_asvs_nodes(conn):
    rows = conn.execute(
        """
        SELECT n.id, n.name, n.section_id, n.section, c.external_id
        FROM node n
        JOIN cre_node_links l ON l.node = n.id
        JOIN cre c ON c.id = l.cre
        WHERE n.name LIKE '%ASVS%'
        ORDER BY n.section_id, c.external_id
        """
    ).fetchall()

    grouped = {}
    for node_id, name, section_id, section, cre_id in rows:
        grouped.setdefault(
            node_id,
            {
                "standard": "ASVS",
                "name": name,
                "section_id": section_id,
                "section": section,
                "cre_ids": [],
            },
        )["cre_ids"].append(cre_id)

    result = []
    identities = set()
    for node in grouped.values():
        key = (node["name"], node["section_id"])
        if key in identities:
            raise ValueError(f"Duplicate ASVS database-node identity: {key}")
        identities.add(key)
        node["cre_ids"] = sorted(set(node["cre_ids"]))
        result.append(node)

    return result


def fetch_repin_candidates(conn):
    rows = conn.execute(
        """
        SELECT n.id, n.name, n.section_id,
               COUNT(DISTINCT c.external_id) AS cre_count
        FROM node n
        JOIN cre_node_links l ON l.node = n.id
        JOIN cre c ON c.id = l.cre
        WHERE n.section IS NOT NULL
          AND length(n.section) > 20
          AND (
              n.name LIKE '%Top 10 2021%'
              OR n.name LIKE '%CWE%'
          )
        GROUP BY n.id
        HAVING COUNT(DISTINCT c.external_id) BETWEEN 2 AND 4
        ORDER BY n.name, n.section_id
        LIMIT 15
        """
    ).fetchall()

    return [
        {"node_id": node_id, "name": name, "section_id": section_id}
        for node_id, name, section_id, _ in rows
    ]


def validate_outputs(source_nodes, curated):
    required_node_fields = {"standard", "name", "section_id", "section", "cre_ids"}
    nodes_by_key = {}

    for index, node in enumerate(source_nodes):
        if not isinstance(node, dict):
            raise ValueError(f"Source node {index} must be an object.")

        missing = required_node_fields - set(node)
        if missing:
            raise ValueError(
                f"Source node {index} is missing fields: {sorted(missing)}"
            )

        for field in ("standard", "name", "section_id", "section"):
            if not isinstance(node[field], str):
                raise ValueError(f"Source node {index}: {field} must be a string.")

        if not node["name"].strip() or not node["section_id"].strip():
            raise ValueError(f"Source node {index} has an empty identity.")

        cre_ids = node["cre_ids"]
        if (
            not isinstance(cre_ids, list)
            or not cre_ids
            or any(not isinstance(value, str) or not value for value in cre_ids)
        ):
            raise ValueError(f"Source node {index} has invalid CRE IDs.")

        if cre_ids != sorted(set(cre_ids)):
            raise ValueError(
                f"Source node CRE IDs must be sorted and unique: "
                f"{(node['name'], node['section_id'])}"
            )

        key = (node["name"], node["section_id"])
        if key in nodes_by_key:
            raise ValueError(f"Duplicate source-node identity: {key}")
        nodes_by_key[key] = node

    if set(curated) != set(CURATED_FIELDS):
        raise ValueError("Curated fixture sections do not match the expected schema.")

    for section, required_fields in CURATED_FIELDS.items():
        records = curated[section]
        if not isinstance(records, list):
            raise ValueError(f"Curated section {section} must be a list.")

        for index, record in enumerate(records):
            if not isinstance(record, dict):
                raise ValueError(
                    f"Curated record {section}[{index}] must be an object."
                )
            missing = required_fields - set(record)
            if missing:
                raise ValueError(
                    f"Curated record {section}[{index}] is missing fields: "
                    f"{sorted(missing)}"
                )

    pins = curated["multilink_pins"]
    pin_keys = [(pin["name"], pin["section_id"]) for pin in pins]
    if len(pin_keys) != len(set(pin_keys)):
        raise ValueError("Duplicate multilink pins.")

    for key in pin_keys:
        node = nodes_by_key.get(key)
        if node is None:
            raise ValueError(f"Pinned node missing from output: {key}")

        cre_ids = node["cre_ids"]
        if not 2 <= len(cre_ids) <= 4:
            raise ValueError(f"Invalid CRE count for pinned node: {key}")


def write_outputs_atomically(output_dir, files):
    """Stage all files first and restore prior files if replacement fails."""
    output_dir.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(
        prefix=".golden-dataset-refresh-",
        dir=output_dir,
    ) as staging_name:
        staging_dir = Path(staging_name)
        staged = {}
        backups = {}

        for filename, data in files.items():
            staged_path = staging_dir / filename
            staged_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            # Verify that every staged file can be parsed before replacement.
            json.loads(staged_path.read_text(encoding="utf-8"))
            staged[filename] = staged_path

        for filename in files:
            destination = output_dir / filename
            if destination.exists():
                backup = staging_dir / f"{filename}.backup"
                shutil.copy2(destination, backup)
                backups[filename] = backup

        replaced = []
        try:
            for filename, staged_path in staged.items():
                os.replace(staged_path, output_dir / filename)
                replaced.append(filename)
        except Exception as error:
            rollback_errors = []
            for filename in reversed(replaced):
                destination = output_dir / filename
                try:
                    if filename in backups:
                        os.replace(backups[filename], destination)
                    elif destination.exists():
                        destination.unlink()
                except OSError as rollback_error:
                    rollback_errors.append(f"{filename}: {rollback_error}")

            if rollback_errors:
                raise RuntimeError(
                    "Output replacement failed and rollback was incomplete: "
                    + "; ".join(rollback_errors)
                ) from error
            raise


def refresh(args):
    output_dir = Path(args.out_dir)

    current_curated = load_json(DEFAULT_INPUTS / "curated.json")
    old_nodes = load_json(DEFAULT_INPUTS / "source_nodes.json")
    old_nodes_by_key = {(node["name"], node["section_id"]): node for node in old_nodes}

    preserved_pins = []

    conn = sqlite3.connect(args.db)
    try:
        asvs_nodes = fetch_asvs_nodes(conn)

        if args.repin:
            candidates = fetch_repin_candidates(conn)
            pins = [
                {"name": node["name"], "section_id": node["section_id"]}
                for node in candidates
            ]
            pin_nodes = []
            for candidate in candidates:
                database_node = fetch_node_by_id(conn, candidate["node_id"])
                if database_node is None:
                    raise ValueError(
                        f"Repinned node missing from database: "
                        f"{candidate['node_id']}"
                    )
                pin_nodes.append(database_node)
        else:
            pins = current_curated["multilink_pins"]
            pin_nodes = []

            for pin in pins:
                key = (pin["name"], pin["section_id"])
                database_node = fetch_node(conn, *key)
                snapshot_node = old_nodes_by_key.get(key)

                if snapshot_node is None:
                    raise ValueError(f"Pinned node missing from snapshot: {key}")

                if database_node != snapshot_node:
                    pin_nodes.append(snapshot_node)
                    preserved_pins.append(key)
                else:
                    pin_nodes.append(database_node)
    finally:
        conn.close()

    nodes_by_key = {}
    for node in asvs_nodes + pin_nodes:
        key = (node["name"], node["section_id"])
        existing = nodes_by_key.get(key)
        if existing is not None and existing != node:
            raise ValueError(f"Conflicting source-node identity: {key}")
        nodes_by_key[key] = node

    source_nodes = sorted(
        nodes_by_key.values(),
        key=lambda node: (
            node["standard"],
            node["name"],
            node["section_id"],
        ),
    )

    curated = dict(current_curated)
    curated["multilink_pins"] = pins

    validate_outputs(source_nodes, curated)

    counts = {
        "source_nodes": len(source_nodes),
        "asvs": sum(node["standard"] == "ASVS" for node in source_nodes),
        "cwe_multilink": sum(node["standard"] == "CWE" for node in source_nodes),
        "explicit": len(curated["explicit"]),
        "update": len(curated["update"]),
        "ambiguous": len(curated["ambiguous"]),
        "cheatsheet_fixtures": len(curated["cheatsheet_fixtures"]),
        "multilink_pins": len(pins),
    }

    mode = "repin" if args.repin else "preserve_existing_pins"
    if args.repin:
        source_description = (
            "ASVS facts refreshed from the configured SQLite database. "
            "Multi-link pins were reselected using the original candidate query. "
            "Curated examples and Cheat Sheet mappings were preserved."
        )
    else:
        source_description = (
            "ASVS facts refreshed from the configured SQLite database. "
            f"{len(preserved_pins)} missing or changed pinned-node snapshots "
            "were preserved from the existing fixtures. "
            "Curated examples and Cheat Sheet mappings were preserved."
        )

    manifest = {
        "schema_version": "0.1.0",
        "refreshed_at": datetime.now(timezone.utc).isoformat(),
        "source": source_description,
        "refresh_mode": mode,
        "preserved_multilink_pins": len(preserved_pins),
        "record_counts": counts,
    }

    files = {
        "source_nodes.json": source_nodes,
        "curated.json": curated,
        "manifest.json": manifest,
    }

    write_outputs_atomically(output_dir, files)

    print(f"Refreshed {len(source_nodes)} source nodes into {output_dir}")
    print(f"Multi-link pins: {len(pins)}")
    print(f"ASVS nodes: {counts['asvs']}")
    print(f"Refresh mode: {mode}")
    print(f"Historical pins preserved: {len(preserved_pins)}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", default=str(DEFAULT_DB))
    parser.add_argument(
        "--out-dir",
        default=str(DEFAULT_INPUTS),
    )
    parser.add_argument(
        "--repin",
        action="store_true",
        help="reselect the 15 multi-link nodes using the original query",
    )
    args = parser.parse_args()
    refresh(args)


if __name__ == "__main__":
    main()
