from __future__ import annotations

import csv
import logging
import re
from collections import deque
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import quote

import requests

CRE_ID_RE = re.compile(r"^\d{3}-\d{3}$")
LTYPE_PART_OF = "Is Part Of"
LTYPE_CONTAINS = "Contains"
CELL_SEP = "|"

logger = logging.getLogger("cres_csv_export")


def _norm_base_url(base_url: str) -> str:
    return base_url.rstrip("/")


def _load_lines(path: str) -> list[str]:
    if not path:
        return []
    values: list[str] = []
    for raw in Path(path).read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        values.append(line)
    return values


def _dedupe_keep_order(values: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        out.append(value)
    return out


def _collect_target_cre_ids(
    *,
    base_url: str,
    timeout_seconds: int,
    direct_cre_ids: list[str],
    standard_names: list[str],
) -> list[str]:
    if direct_cre_ids:
        valid = [x for x in direct_cre_ids if CRE_ID_RE.match(x)]
        invalid = sorted(set(direct_cre_ids) - set(valid))
        if invalid:
            raise ValueError(f"Invalid CRE IDs: {', '.join(invalid)}")
        logger.info("Using %s CRE IDs from explicit filter", len(valid))
        return _dedupe_keep_order(valid)

    if standard_names:
        logger.info(
            "Resolving CREs from %s standard filters: %s",
            len(standard_names),
            ", ".join(standard_names),
        )
        cre_ids: list[str] = []
        for idx, standard in enumerate(standard_names, start=1):
            encoded = quote(standard, safe="")
            resp = requests.get(
                f"{base_url}/standard/{encoded}",
                timeout=timeout_seconds,
            )
            resp.raise_for_status()
            payload = resp.json()
            rows = payload.get("standards") or []
            before = len(cre_ids)
            for row in rows:
                for link in row.get("links") or []:
                    doc = link.get("document") or {}
                    doctype = str(doc.get("doctype", "")).upper()
                    doc_id = str(doc.get("id", "")).strip()
                    if doctype == "CRE" and CRE_ID_RE.match(doc_id):
                        cre_ids.append(doc_id)
            logger.info(
                "[%s/%s] standard '%s' contributed %s linked CRE references",
                idx,
                len(standard_names),
                standard,
                len(cre_ids) - before,
            )
        return _dedupe_keep_order(cre_ids)

    logger.info("No filters provided; discovering full CRE taxonomy via /all_cres")
    page = 1
    per_page = 200
    all_ids: list[str] = []
    while True:
        resp = requests.get(
            f"{base_url}/all_cres",
            params={"page": page, "per_page": per_page},
            timeout=timeout_seconds,
        )
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("data") or []
        for row in rows:
            cid = str(row.get("id", "")).strip()
            if CRE_ID_RE.match(cid):
                all_ids.append(cid)
        total_pages = int(payload.get("total_pages") or 1)
        logger.info(
            "Discovered page %s/%s from /all_cres (running CRE IDs: %s)",
            page,
            total_pages,
            len(all_ids),
        )
        if page >= total_pages:
            break
        page += 1
    return _dedupe_keep_order(all_ids)


def _doc_is_cre(doc: dict[str, Any]) -> bool:
    return str(doc.get("doctype", "")).upper() == "CRE"


def _cre_external_id(doc: dict[str, Any]) -> str:
    return str(doc.get("id", "")).strip()


def _parent_cre_ids(cre_payload: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for link in cre_payload.get("links") or []:
        if str(link.get("ltype", "")) != LTYPE_PART_OF:
            continue
        doc = link.get("document") or {}
        cid = _cre_external_id(doc)
        if _doc_is_cre(doc) and CRE_ID_RE.match(cid):
            out.append(cid)
    return _dedupe_keep_order(out)


def _child_cre_ids(cre_payload: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for link in cre_payload.get("links") or []:
        if str(link.get("ltype", "")) != LTYPE_CONTAINS:
            continue
        doc = link.get("document") or {}
        cid = _cre_external_id(doc)
        if _doc_is_cre(doc) and CRE_ID_RE.match(cid):
            out.append(cid)
    return _dedupe_keep_order(out)


def _fetch_cre(
    *,
    base_url: str,
    cre_id: str,
    timeout_seconds: int,
    cache: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if cre_id in cache:
        return cache[cre_id]
    resp = requests.get(
        f"{base_url}/id/{quote(cre_id, safe='')}",
        timeout=timeout_seconds,
    )
    resp.raise_for_status()
    payload = resp.json()
    cre = payload.get("data") or {}
    cache[cre_id] = cre
    return cre


def _build_ancestor_closure(
    *,
    base_url: str,
    timeout_seconds: int,
    seed_ids: list[str],
) -> dict[str, dict[str, Any]]:
    cache: dict[str, dict[str, Any]] = {}
    pending = deque(_dedupe_keep_order(seed_ids))
    while pending:
        cid = pending.popleft()
        if cid in cache:
            continue
        cre = _fetch_cre(
            base_url=base_url,
            cre_id=cid,
            timeout_seconds=timeout_seconds,
            cache=cache,
        )
        for p in _parent_cre_ids(cre):
            if p not in cache:
                pending.append(p)
    return cache


def _roots(parents: dict[str, list[str]], all_ids: Iterable[str]) -> set[str]:
    return {cid for cid in all_ids if not parents.get(cid)}


def _bfs_dist_to_target(parents: dict[str, list[str]], target: str) -> dict[str, int]:
    dist: dict[str, int] = {target: 0}
    q: deque[str] = deque([target])
    while q:
        n = q.popleft()
        for p in parents.get(n, []):
            nd = dist[n] + 1
            if p not in dist or nd < dist[p]:
                dist[p] = nd
                q.append(p)
    return dist


def _shortest_paths_to_target(
    *,
    parents: dict[str, list[str]],
    children: dict[str, list[str]],
    roots: set[str],
    target: str,
) -> list[list[str]]:
    dist = _bfs_dist_to_target(parents, target)
    reachable = [r for r in roots if r in dist]
    if not reachable:
        return [[target]]

    l_min = min(dist[r] for r in reachable)
    start_roots = [r for r in reachable if dist[r] == l_min]

    def down_toward_t(n: str) -> list[str]:
        dn = dist.get(n, 10**9)
        out_ch: list[str] = []
        for c in children.get(n, []):
            if dist.get(c, 10**9) == dn - 1:
                out_ch.append(c)
        return out_ch

    paths: list[list[str]] = []

    def dfs(node: str, acc: list[str]) -> None:
        acc.append(node)
        if node == target:
            paths.append(list(acc))
        else:
            for c in down_toward_t(node):
                dfs(c, acc)
        acc.pop()

    for r in start_roots:
        dfs(r, [])
    seen: set[tuple[str, ...]] = set()
    uniq: list[list[str]] = []
    for p in paths:
        t = tuple(p)
        if t in seen:
            continue
        seen.add(t)
        uniq.append(p)
    return uniq


def _std_key_id(name: str) -> str:
    return f"{name}{CELL_SEP}id"


def _std_key_name(name: str) -> str:
    return f"{name}{CELL_SEP}name"


def _std_key_section(name: str) -> str:
    return f"{name}{CELL_SEP}section"


def _std_key_hyperlink(name: str) -> str:
    return f"{name}{CELL_SEP}hyperlink"


def _std_key_description(name: str) -> str:
    return f"{name}{CELL_SEP}description"


def _std_key_version(name: str) -> str:
    return f"{name}{CELL_SEP}version"


def _std_key_tooltype(name: str) -> str:
    return f"{name}{CELL_SEP}tooltype"


def _std_key_linktype(name: str) -> str:
    return f"{name}{CELL_SEP}link_type"


def _gather_standard_links(
    cre_payload: dict[str, Any], standard_name_filter: set[str]
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for link in cre_payload.get("links") or []:
        doc = link.get("document") or {}
        if _doc_is_cre(doc):
            continue
        sname = str(doc.get("name", "")).strip()
        if not sname:
            continue
        if standard_name_filter and sname not in standard_name_filter:
            continue
        rows.append(
            {
                "name": sname,
                "sectionID": str(doc.get("sectionID", "") or "").strip(),
                "section": str(doc.get("section", "") or "").strip(),
                "subsection": str(doc.get("subsection", "") or "").strip(),
                "hyperlink": str(doc.get("hyperlink", "") or "").strip(),
                "description": str(doc.get("description", "") or "").strip(),
                "version": str(doc.get("version", "") or "").strip(),
                "tooltype": str(doc.get("tooltype", "") or "").strip(),
                "ltype": str(link.get("ltype", "") or "").strip(),
            }
        )
    rows.sort(
        key=lambda r: (
            r["name"],
            r["sectionID"],
            r["section"],
            r["subsection"],
            r["hyperlink"],
            r["description"],
            r["version"],
            r["tooltype"],
            r["ltype"],
        )
    )
    return rows


def _aggregate_standard_columns(
    links: list[dict[str, Any]],
) -> tuple[dict[str, str], set[str]]:
    by_name: dict[str, list[dict[str, Any]]] = {}
    for row in links:
        by_name.setdefault(row["name"], []).append(row)

    out: dict[str, str] = {}
    keys: set[str] = set()

    for sname, group in sorted(by_name.items()):
        ids = CELL_SEP.join(r["sectionID"] for r in group)
        names = CELL_SEP.join(r["section"] for r in group)
        sections = CELL_SEP.join(r["subsection"] for r in group)
        hls = CELL_SEP.join(r["hyperlink"] for r in group)
        descs = CELL_SEP.join(r["description"] for r in group)
        vers = CELL_SEP.join(r["version"] for r in group)
        ttypes = CELL_SEP.join(r["tooltype"] for r in group)
        ltypes = CELL_SEP.join(r["ltype"] for r in group)

        out[_std_key_id(sname)] = ids
        out[_std_key_name(sname)] = names
        out[_std_key_section(sname)] = sections
        out[_std_key_hyperlink(sname)] = hls
        out[_std_key_description(sname)] = descs
        out[_std_key_version(sname)] = vers
        out[_std_key_tooltype(sname)] = ttypes
        out[_std_key_linktype(sname)] = ltypes
        keys.update(
            {
                _std_key_id(sname),
                _std_key_name(sname),
                _std_key_section(sname),
                _std_key_hyperlink(sname),
                _std_key_description(sname),
                _std_key_version(sname),
                _std_key_tooltype(sname),
                _std_key_linktype(sname),
            }
        )

    return out, keys


def _cre_cell(cre_payload: dict[str, Any]) -> str:
    cid = str(cre_payload.get("id", "")).strip()
    cname = str(cre_payload.get("name", "")).strip()
    return f"{cid}{CELL_SEP}{cname}"


def _path_to_cre_row(
    path: list[str],
    cache: dict[str, dict[str, Any]],
    *,
    max_depth: int,
    standard_name_filter: set[str],
) -> tuple[dict[str, str], set[str]]:
    leaf = path[-1]
    leaf_payload = cache[leaf]
    tags = sorted(
        str(t).strip() for t in (leaf_payload.get("tags") or []) if str(t).strip()
    )
    desc = str(leaf_payload.get("description", "") or "").strip()

    row: dict[str, str] = {
        "CRE Description": desc,
        "CRE Tags": ";".join(tags),
    }
    for i in range(max_depth + 1):
        key = f"CRE {i}"
        row[key] = _cre_cell(cache[path[i]]) if i < len(path) else ""

    std_links = _gather_standard_links(leaf_payload, standard_name_filter)
    std_cols, std_keys = _aggregate_standard_columns(std_links)
    row.update(std_cols)
    return row, std_keys


def export_cres_and_standards_csv(
    *,
    output_path: str,
    base_url: str = "https://opencre.org/rest/v1",
    timeout_seconds: int = 30,
    cre_ids: list[str] | None = None,
    standards: list[str] | None = None,
    progress_every: int = 25,
) -> int:
    base_url = _norm_base_url(base_url)
    timeout_seconds = max(1, int(timeout_seconds))
    progress_every = max(1, int(progress_every))
    target_cre_ids = _collect_target_cre_ids(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        direct_cre_ids=_dedupe_keep_order(cre_ids or []),
        standard_names=_dedupe_keep_order(standards or []),
    )
    if not target_cre_ids:
        raise RuntimeError("No CRE IDs selected with the given filters")

    standard_name_filter = set(standards or [])
    cache = _build_ancestor_closure(
        base_url=base_url,
        timeout_seconds=timeout_seconds,
        seed_ids=target_cre_ids,
    )
    all_graph_ids = list(cache.keys())
    parents: dict[str, list[str]] = {
        cid: _parent_cre_ids(cache[cid]) for cid in all_graph_ids
    }
    children: dict[str, list[str]] = {
        cid: _child_cre_ids(cache[cid]) for cid in all_graph_ids
    }
    roots = _roots(parents, all_graph_ids)

    max_path_len = 1
    all_paths: list[tuple[str, list[str]]] = []
    for t in target_cre_ids:
        paths = _shortest_paths_to_target(
            parents=parents,
            children=children,
            roots=roots,
            target=t,
        )
        for p in paths:
            max_path_len = max(max_path_len, len(p))
            all_paths.append((t, p))

    max_depth = max_path_len - 1
    cre_cols = [f"CRE {i}" for i in range(max_depth + 1)]
    fixed_tail = ["CRE Description", "CRE Tags"]

    rows_out: list[dict[str, str]] = []
    std_header_keys: set[str] = set()

    for idx, (_, path) in enumerate(all_paths, start=1):
        leaf_payload = cache[path[-1]]
        std_links = _gather_standard_links(leaf_payload, standard_name_filter)
        if standard_name_filter and not std_links:
            if idx % progress_every == 0:
                logger.info(
                    "Progress %s/%s path rows (written: %s)",
                    idx,
                    len(all_paths),
                    len(rows_out),
                )
            continue

        row, sk = _path_to_cre_row(
            path,
            cache,
            max_depth=max_depth,
            standard_name_filter=standard_name_filter,
        )
        std_header_keys |= sk
        rows_out.append(row)
        if idx % progress_every == 0 or idx == len(all_paths):
            logger.info(
                "Progress %s/%s path rows (written: %s)",
                idx,
                len(all_paths),
                len(rows_out),
            )

    if not rows_out:
        raise RuntimeError("No rows matched. Try relaxing filters.")

    std_cols_sorted = sorted(std_header_keys)
    fieldnames = [*cre_cols, *fixed_tail, *std_cols_sorted]
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows_out:
            writer.writerow({k: row.get(k, "") for k in fieldnames})
    logger.info("Wrote %s rows to %s", len(rows_out), out_path)
    return len(rows_out)
