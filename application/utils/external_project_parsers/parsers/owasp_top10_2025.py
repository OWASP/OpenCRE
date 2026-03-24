import json
from pathlib import Path

from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client
from application.utils.external_project_parsers.base_parser_defs import (
    ParseResult,
    ParserInterface,
)


class OwaspTop10_2025(ParserInterface):
    name = "OWASP Top 10 2025"
    data_file = (
        Path(__file__).resolve().parent.parent / "data" / "owasp_top10_2025.json"
    )

    def parse(self, cache: db.Node_collection, ph: prompt_client.PromptHandler):
        with self.data_file.open("r", encoding="utf-8") as handle:
            raw_entries = json.load(handle)

        entries = []
        for entry in raw_entries:
            standard = defs.Standard(
                name=self.name,
                sectionID=entry["section_id"],
                section=entry["section"],
                hyperlink=entry["hyperlink"],
            )
            for cre_id in entry.get("cre_ids", []):
                cres = cache.get_CREs(external_id=cre_id)
                if not cres:
                    continue
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
