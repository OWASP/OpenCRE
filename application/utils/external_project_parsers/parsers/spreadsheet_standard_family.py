"""Shared logic for extracting one standard family from master spreadsheet rows."""

from copy import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from application.defs import cre_defs as defs
from application.utils.external_project_parsers import base_parser_defs


def is_empty(value: Optional[str]) -> bool:
    value = str(value).strip()
    return (
        value == "None"
        or value == ""
        or "n/a" in value.lower()
        or value == "nan"
        or value.lower() == "no"
        or value.lower() == "tbd"
        or value.lower() == "see higher level topic"
        or value.lower() == "tbd"
        or value.lower() == "0"
    )


def parse_standards_for_family(
    mapping: Dict[str, str],
    name: str,
    struct: Dict[str, Any],
) -> List[defs.Link]:
    links: List[defs.Link] = []
    if not is_empty(mapping.get(struct["section"])) or not is_empty(
        mapping.get(struct["sectionID"])
    ):
        if "separator" in struct:
            separator = struct["separator"]
            sections = str(mapping.pop(struct["section"])).split(separator)
            subsections = str(mapping.get(struct["subsection"], "")).split(separator)

            hyperlinks = str(mapping.get(struct["hyperlink"], "")).split(separator)
            if len(sections) > len(subsections):
                subsections.extend([""] * (len(sections) - len(subsections)))
            if len(sections) > len(hyperlinks):
                hyperlinks.extend([""] * (len(sections) - len(hyperlinks)))

            sectionIDs = [""] * len(sections)
            if struct["sectionID"] in mapping:
                sectionIDs = str(mapping.pop(struct["sectionID"])).split(separator)
            if len(sections) > len(sectionIDs):
                sectionIDs.extend([""] * (len(sections) - len(sectionIDs)))

            if len(sections) == 0:
                sections = [""] * len(sectionIDs)

            for section, subsection, link, sectionID in zip(
                sections, subsections, hyperlinks, sectionIDs
            ):
                if not is_empty(section):
                    links.append(
                        defs.Link(
                            ltype=defs.LinkTypes.LinkedTo,
                            document=defs.Standard(
                                name=name,
                                section=section.strip(),
                                hyperlink=link.strip(),
                                subsection=subsection.strip(),
                                sectionID=str(sectionID).strip(),
                            ),
                        )
                    )
        else:
            section = str(mapping.get(struct["section"], ""))
            subsection = str(mapping.get(struct["subsection"], ""))
            hyperlink = str(mapping.get(struct["hyperlink"], ""))
            sectionID = str(mapping.get(struct["sectionID"], ""))

            links.append(
                defs.Link(
                    ltype=defs.LinkTypes.LinkedTo,
                    document=defs.Standard(
                        name=name,
                        section=section.strip(),
                        sectionID=sectionID.strip(),
                        subsection=subsection.strip(),
                        hyperlink=hyperlink.strip(),
                    ),
                )
            )
    return links


@dataclass
class SpreadsheetStandardFamilyParser:
    family_name: str
    struct: Dict[str, Any]

    def _tagged(self, std: defs.Standard) -> defs.Standard:
        # Spreadsheet-derived standards are requirements-level mappings.
        # Source tag is derived from the family name.
        source = (
            str(self.family_name)
            .lower()
            .replace("owasp ", "owasp_")
            .replace(" ", "_")
            .replace("-", "_")
            .replace("(", "")
            .replace(")", "")
            .replace("/", "_")
        )
        if source == "asvs":
            source = "owasp_asvs"
        elif source == "cwe":
            source = "cwe"
        elif source == "iso_27001":
            source = "iso27001"

        std.tags = base_parser_defs.build_tags(
            family=base_parser_defs.Family.STANDARD,
            subtype=base_parser_defs.Subtype.REQUIREMENTS_STANDARD,
            audience=base_parser_defs.Audience.DEVELOPER,
            maturity=base_parser_defs.Maturity.STABLE,
            source=source,
            extra=std.tags,
        )
        return std

    def parse_rows(
        self, rows_with_cre: List[Tuple[Dict[str, str], defs.CRE]]
    ) -> List[defs.Standard]:
        docs: List[defs.Standard] = []
        for mapping, cre in rows_with_cre:
            docs.extend(self.parse_row(mapping, cre))
        return docs

    def parse_row(self, mapping: Dict[str, str], cre: defs.CRE) -> List[defs.Standard]:
        row_copy = copy(mapping)
        links = parse_standards_for_family(row_copy, self.family_name, self.struct)
        family_docs: List[defs.Standard] = []
        for link in links:
            doc = self._tagged(link.document).add_link(
                defs.Link(document=cre.shallow_copy(), ltype=defs.LinkTypes.LinkedTo)
            )
            family_docs.append(doc)
        return family_docs
