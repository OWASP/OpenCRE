import ast
import logging
import os
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import parse_qs, urlparse

from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client as prompt_client
from application.utils import git
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


OPENCRE_LINK_RE = re.compile(
    r"https?://(?:www\.)?opencre\.org/cre/\d+-\d+(?:\?[^\s\)\]\}]+)?",
    re.IGNORECASE,
)


class SKF(ParserInterface):
    name = "OWASP Security Knowledge Framework"
    repo_url = "https://github.com/blabla1337/skf-flask.git"
    kb_root = "skf/markdown/knowledge_base"
    code_root = "skf/markdown/code_examples"
    initial_data = "skf/initial_data.py"

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        if not cache:
            raise ValueError("SKF parser called with null db(cache) argument")
        repo = git.clone(self.repo_url)
        branch = getattr(repo, "active_branch", None)
        branch_name = branch.name if branch else "main"
        repo_base = self.repo_url.replace(".git", "")

        results: Dict[str, List[defs.Document]] = {}

        kb_entries = self.parse_knowledge_base(
            repo_path=repo.working_dir,
            branch=branch_name,
            repo_base=repo_base,
            cache=cache,
        )
        if kb_entries:
            results["SKF Knowledge Base"] = kb_entries

        code_entries = self.parse_code_examples(
            repo_path=repo.working_dir,
            branch=branch_name,
            repo_base=repo_base,
            cache=cache,
        )
        if code_entries:
            results["SKF Code Examples"] = code_entries

        lab_entries = self.parse_lab_items(
            repo_path=repo.working_dir,
            branch=branch_name,
            repo_base=repo_base,
            cache=cache,
        )
        if lab_entries:
            results["SKF Labs"] = lab_entries

        return ParseResult(results=results)

    def parse_knowledge_base(
        self, repo_path: str, branch: str, repo_base: str, cache: db.Node_collection
    ) -> List[defs.Standard]:
        entries: List[defs.Standard] = []
        kb_root = os.path.join(repo_path, self.kb_root)
        if not os.path.isdir(kb_root):
            logger.warning("SKF knowledge base directory not found: %s", kb_root)
            return entries

        for root, _, files in os.walk(kb_root):
            rel_dir = os.path.relpath(root, kb_root)
            if rel_dir.startswith("web_old"):
                continue
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                cre_links = self._extract_opencre_links(text)
                if not cre_links:
                    continue
                section_id, title = self._parse_kb_filename(fname)
                hyperlink = self._make_repo_link(
                    repo_base=repo_base, branch=branch, repo_path=repo_path, path=fpath
                )
                tags = self._merge_tags(
                    ["knowledge-base"] + self._path_tags(rel_dir), []
                )
                default_meta = {
                    "name": "OWASP Security Knowledge Framework Knowledge Base",
                    "section": title,
                    "section_id": section_id,
                    "subsection": self._normalize_subsection(rel_dir),
                    "hyperlink": hyperlink,
                    "description": "",
                    "version": "",
                    "tags": tags,
                    "doctype": "standard",
                    "tool_type": None,
                }
                entries.extend(
                    self._build_entries_for_links(
                        cre_links=cre_links,
                        default_meta=default_meta,
                        cache=cache,
                        default_tool_type=None,
                    )
                )
        return entries

    def parse_code_examples(
        self, repo_path: str, branch: str, repo_base: str, cache: db.Node_collection
    ) -> List[defs.Standard]:
        entries: List[defs.Standard] = []
        code_root = os.path.join(repo_path, self.code_root)
        if not os.path.isdir(code_root):
            logger.warning("SKF code examples directory not found: %s", code_root)
            return entries

        for root, _, files in os.walk(code_root):
            rel_dir = os.path.relpath(root, code_root)
            for fname in files:
                if not fname.endswith(".md"):
                    continue
                fpath = os.path.join(root, fname)
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    text = f.read()
                cre_links = self._extract_opencre_links(text)
                if not cre_links:
                    continue
                section_id, title_from_name = self._parse_code_filename(fname)
                title = self._extract_h1(text) or title_from_name
                hyperlink = self._make_repo_link(
                    repo_base=repo_base, branch=branch, repo_path=repo_path, path=fpath
                )
                tags = self._merge_tags(["code-example"] + self._path_tags(rel_dir), [])
                default_meta = {
                    "name": "OWASP Security Knowledge Framework Code Examples",
                    "section": title,
                    "section_id": section_id,
                    "subsection": self._normalize_subsection(rel_dir),
                    "hyperlink": hyperlink,
                    "description": "",
                    "version": "",
                    "tags": tags,
                    "doctype": "standard",
                    "tool_type": None,
                }
                entries.extend(
                    self._build_entries_for_links(
                        cre_links=cre_links,
                        default_meta=default_meta,
                        cache=cache,
                        default_tool_type=None,
                    )
                )
        return entries

    def parse_lab_items(
        self, repo_path: str, branch: str, repo_base: str, cache: db.Node_collection
    ) -> List[defs.Tool]:
        entries: List[defs.Tool] = []
        lab_path = os.path.join(repo_path, self.initial_data)
        if not os.path.isfile(lab_path):
            logger.warning("SKF initial data file not found: %s", lab_path)
            return entries

        with open(lab_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        lab_items = self._parse_lab_items(text)
        for title, link, level, image_tag, label, has_hints in lab_items:
            text_blob = " ".join(
                [
                    str(x)
                    for x in [title, link, level, image_tag, label, has_hints]
                    if x is not None
                ]
            )
            cre_links = self._extract_opencre_links(text_blob)
            if not cre_links:
                continue
            tags = self._merge_tags(
                [label, image_tag, f"level-{level}"],
                [],
            )
            default_meta = {
                "name": "OWASP Security Knowledge Framework Labs",
                "section": title,
                "section_id": label,
                "subsection": "",
                "hyperlink": link,
                "description": "",
                "version": "",
                "tags": tags,
                "doctype": "tool",
                "tool_type": defs.ToolTypes.Training.value,
            }
            entries.extend(
                self._build_entries_for_links(
                    cre_links=cre_links,
                    default_meta=default_meta,
                    cache=cache,
                    default_tool_type=defs.ToolTypes.Training.value,
                )
            )
        return entries

    def _parse_lab_items(
        self, text: str
    ) -> List[Tuple[str, str, int, str, str, Optional[bool]]]:
        items: List[Tuple[str, str, int, str, str, Optional[bool]]] = []
        try:
            tree = ast.parse(text)
        except SyntaxError:
            logger.warning("SKF initial_data.py failed to parse, skipping lab items")
            return items

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if not getattr(node.func, "id", "") == "LabItem":
                continue
            if len(node.args) < 6:
                continue
            values = [self._ast_constant(arg) for arg in node.args[:6]]
            if any(v is None for v in values[:5]):
                continue
            items.append(  # type: ignore[arg-type]
                (
                    values[0],
                    values[1],
                    values[2],
                    values[3],
                    values[4],
                    values[5],
                )
            )
        return items

    @staticmethod
    def _ast_constant(node):
        if isinstance(node, ast.Constant):
            return node.value
        return None

    def _extract_opencre_links(self, text: str) -> List[str]:
        links = []
        for match in OPENCRE_LINK_RE.finditer(text):
            url = match.group(0).rstrip(").,;")
            links.append(url)
        return links

    def _build_entries_for_links(
        self,
        cre_links: List[str],
        default_meta: Dict[str, object],
        cache: db.Node_collection,
        default_tool_type: Optional[str],
    ) -> List[defs.Document]:
        entries: Dict[Tuple, defs.Document] = {}
        for url in cre_links:
            cre_id, params = self._parse_cre_link(url)
            if not cre_id:
                continue
            meta = self._merge_meta(default_meta, params)
            doc = self._get_or_create_entry(
                entries=entries,
                meta=meta,
                default_tool_type=default_tool_type,
            )
            linked = self._link_cres(doc, cache, cre_id)
            if not linked:
                logger.debug("SKF link missing CRE %s for %s", cre_id, meta.get("name"))
        return list(entries.values())

    def _get_or_create_entry(
        self,
        entries: Dict[Tuple, defs.Document],
        meta: Dict[str, object],
        default_tool_type: Optional[str],
    ) -> defs.Document:
        doctype = meta.get("doctype", "standard").lower()
        name = meta.get("name", "")
        section = meta.get("section", "")
        section_id = meta.get("section_id", "")
        subsection = meta.get("subsection", "")
        hyperlink = meta.get("hyperlink", "")
        description = meta.get("description", "")
        version = meta.get("version", "")
        tags = meta.get("tags", [])
        tool_type = meta.get("tool_type") or default_tool_type
        key = (
            doctype,
            name,
            section,
            section_id,
            subsection,
            hyperlink,
            version,
            tool_type,
            tuple(tags),
        )
        if key in entries:
            return entries[key]

        if doctype == "tool":
            tool_type_enum = (
                defs.ToolTypes.from_str(tool_type or defs.ToolTypes.Unknown.value)
                or defs.ToolTypes.Unknown
            )
            doc = defs.Tool(
                name=name,
                section=section,
                sectionID=section_id,
                subsection=subsection,
                hyperlink=hyperlink,
                description=description,
                version=version,
                tags=tags,
                tooltype=tool_type_enum,
            )
        else:
            doc = defs.Standard(
                name=name,
                section=section,
                sectionID=section_id,
                subsection=subsection,
                hyperlink=hyperlink,
                description=description,
                version=version,
                tags=tags,
            )

        entries[key] = doc
        return doc

    def _parse_cre_link(self, url: str) -> Tuple[str, Dict[str, str]]:
        parsed = urlparse(url)
        cre_id = parsed.path.split("/")[-1] if parsed.path else ""
        raw_params = parse_qs(parsed.query or "")
        params = {k.lower(): v[0] for k, v in raw_params.items() if v}
        return cre_id, params

    def _merge_meta(self, default_meta: Dict[str, object], params: Dict[str, str]):
        meta = dict(default_meta)
        if params.get("type"):
            meta["doctype"] = params.get("type").lower()
        if params.get("name"):
            meta["name"] = params.get("name")
        if params.get("section"):
            meta["section"] = params.get("section")
        if params.get("sectionid"):
            meta["section_id"] = params.get("sectionid")
        if params.get("subsection"):
            meta["subsection"] = params.get("subsection")
        if params.get("link"):
            meta["hyperlink"] = params.get("link")
        if params.get("description"):
            meta["description"] = params.get("description")
        if params.get("version"):
            meta["version"] = params.get("version")
        if params.get("tool_type"):
            meta["tool_type"] = params.get("tool_type")
        if params.get("tooltype"):
            meta["tool_type"] = params.get("tooltype")
        if params.get("tags"):
            meta["tags"] = self._merge_tags(meta.get("tags", []), params["tags"])
        return meta

    def _link_cres(
        self, doc: defs.Document, cache: db.Node_collection, cre_id: str
    ) -> bool:
        linked_any = False
        cres = cache.get_CREs(external_id=cre_id)
        for cre in cres:
            if doc.has_link(defs.Link(document=cre, ltype=defs.LinkTypes.LinkedTo)):
                continue
            try:
                doc.add_link(
                    defs.Link(
                        document=cre,
                        ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                    )
                )
                linked_any = True
            except Exception:
                continue
        return linked_any

    def _parse_kb_filename(self, filename: str) -> Tuple[str, str]:
        base = os.path.basename(filename)
        m = re.match(r"(?P<id>\d+)-knowledge_base--(?P<title>.+)--", base)
        if m:
            return m.group("id"), self._humanize_title(m.group("title"))
        return "", self._humanize_title(os.path.splitext(base)[0])

    def _parse_code_filename(self, filename: str) -> Tuple[str, str]:
        base = os.path.basename(filename)
        m = re.match(r"(?P<id>\d+)-code_example--(?P<title>.+)--", base)
        if m:
            return m.group("id"), self._humanize_title(m.group("title"))
        return "", self._humanize_title(os.path.splitext(base)[0])

    def _extract_h1(self, text: str) -> str:
        for line in text.splitlines():
            if line.startswith("# "):
                return line[2:].strip()
        return ""

    def _make_repo_link(
        self, repo_base: str, branch: str, repo_path: str, path: str
    ) -> str:
        rel_path = os.path.relpath(path, repo_path)
        return f"{repo_base}/blob/{branch}/{rel_path}"

    def _humanize_title(self, text: str) -> str:
        title = text.replace("_", " ").replace("-", " ")
        title = re.sub(r"\s+", " ", title).strip()
        return title

    def _merge_tags(self, default_tags: List[str], extra_tags) -> List[str]:
        tags: List[str] = []
        for t in default_tags:
            if t and t not in tags:
                tags.append(t)
        if isinstance(extra_tags, str):
            extra = [t.strip() for t in extra_tags.split(",") if t.strip()]
        else:
            extra = [t for t in extra_tags if t]
        for t in extra:
            if t not in tags:
                tags.append(t)
        return tags

    def _path_tags(self, rel_dir: str) -> List[str]:
        if not rel_dir or rel_dir == ".":
            return []
        return [p for p in rel_dir.split(os.sep) if p and p != "."]

    def _normalize_subsection(self, rel_dir: str) -> str:
        if not rel_dir or rel_dir == ".":
            return ""
        return rel_dir.replace(os.sep, "/")
