import json
from pathlib import Path

from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client
from application.utils.external_project_parsers.base_parser_defs import (
    ParseResult,
    ParserInterface,
)


class OwaspKubernetesTop10_2025(ParserInterface):
    name = "OWASP Kubernetes Top Ten 2025 (Draft)"
    data_file = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "owasp_kubernetes_top10_2025.json"
    )
    fallback_data_file = (
        Path(__file__).resolve().parent.parent
        / "data"
        / "owasp_kubernetes_top10_2022.json"
    )

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        with self.data_file.open("r", encoding="utf-8") as handle:
            raw_entries = json.load(handle)
        with self.fallback_data_file.open("r", encoding="utf-8") as handle:
            fallback_entries = {
                entry["section_id"]: entry for entry in json.load(handle)
            }

        entries = []
        for entry in raw_entries:
            standard = defs.Standard(
                name=self.name,
                sectionID=entry["section_id"],
                section=entry["section"],
                hyperlink=entry["hyperlink"],
            )
            linked_cre_ids = []
            for cre_id in entry.get("cre_ids", []):
                cres = cache.get_CREs(external_id=cre_id)
                if not cres:
                    continue
                linked_cre_ids.append(cre_id)
                standard.add_link(
                    defs.Link(
                        ltype=defs.LinkTypes.LinkedTo,
                        document=cres[0].shallow_copy(),
                    )
                )
            if not linked_cre_ids:
                for section_id in entry.get("fallback_section_ids", []):
                    fallback_entry = fallback_entries.get(section_id)
                    if not fallback_entry:
                        continue
                    for cre_id in fallback_entry.get("cre_ids", []):
                        if cre_id in linked_cre_ids:
                            continue
                        cres = cache.get_CREs(external_id=cre_id)
                        if not cres:
                            continue
                        linked_cre_ids.append(cre_id)
                        standard.add_link(
                            defs.Link(
                                ltype=defs.LinkTypes.LinkedTo,
                                document=cres[0].shallow_copy(),
                            )
                        )
            entries.append(standard)

        return ParseResult(
            results={self.name: entries},
            calculate_gap_analysis=False,
            calculate_embeddings=False,
        )
