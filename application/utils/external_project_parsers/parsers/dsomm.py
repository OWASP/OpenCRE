import re
import yaml
import logging
from application.database import db
from application.defs import cre_defs as defs
from application.prompt_client import prompt_client as prompt_client
import requests
from application.utils.external_project_parsers import base_parser_defs
from application.utils.external_project_parsers.base_parser_defs import (
    ParserInterface,
    ParseResult,
)

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class DSOMM(ParserInterface):
    name = "DevSecOps Maturity Model (DSOMM)"
    # Legacy (previous) aggregated YAML. This URL may move/vanish as the upstream
    # repository reorganizes its generated assets.
    LEGACY_GENERATED_YAML_URL = (
        "https://raw.githubusercontent.com/devsecopsmaturitymodel/DevSecOps-MaturityModel-data/main/src/assets/"
        "YAML/generated/generated.yaml"
    )
    # Current DSOMM YAML layout (activities live under multiple category YAMLs).
    GITHUB_API_DEFAULT_YAML_DIR = (
        "https://api.github.com/repos/devsecopsmaturitymodel/DevSecOps-MaturityModel-data/contents/"
        "src/assets/YAML/default?ref=main"
    )
    means_none = [
        "Not explicitly covered by ISO 27001 - too specific",
        "Not explicitly covered by ISO 27001",
        "May be part of project management",
        "May be part of risk assessment",
        "Mutual review of source code is not explicitly required in ISO 27001 may be",
        "Mutual security testing is not explicitly required in ISO 27001 may be",
        "War games are not explicitly required in ISO 27001 may be",
        "Security champions are missing in ISO 27001 most likely",
        "Security champions are missing in ISO 27001",
        "ISO 27001:2022 mapping is missing",
        "Security consulting is missing in ISO 27001 may be",
        "Peer review - four eyes principle is not explicitly required by ISO 27001",
        "Hardening is not explicitly covered by ISO 27001 - too specific",
        "Virtual environments are not explicitly covered by ISO 27001 - too specific",
        "{'TODO': \"Incorporate advanced WAF input validation processes into the organization's ISMS.\"}",
        "{'TODO': \"Incorporate advanced WAF input validation processes into the organization's ISMS.\"}",
        "{'TODO': 'Integrate WAF deployment with ISO 27001 controls for system hardening.'}",
        "{'TODO': 'Integrate WAF deployment with ISO 27001 controls for system hardening.'}",
        "{'TODO': 'Identify and implement SAMM security practices relevant to WAF configuration.'}",
        "System hardening is not explicitly covered by ISO 27001 - too specific",
        "vcs usage is not explicitly covered by ISO 27001 - too specific",
        "System hardening, virtual environments are not explicitly covered by ISO 27001 - too specific",
    ]
    manual_mappings = {
        "Usage of feature toggles": "344-611",
        "Usage of edge encryption at transit": "435-702",
    }

    def link_to_samm(self, activity, cache, standard):
        # DSOMM fallback parsing (multiple YAML files) can surface duplicate
        # SAMM→CRE link targets. `standard.add_link()` is strict and will
        # raise `DuplicateLinkException` if we attempt to add the same CRE twice,
        # so we dedupe by CRE document id.
        linked_cre_doc_ids = {
            l.document.id for l in (standard.links or []) if getattr(l.document, "id", None)
        }
        for sectionID in activity.get("references").get("samm2"):
            if sectionID in self.means_none:
                continue
            samms = cache.get_nodes(name="SAMM", sectionID=f"{sectionID}")
            if not len(samms):
                sectionID = re.sub("-\d", "", f"{sectionID}")
                samms = cache.get_nodes(name="SAMM", sectionID=f"{sectionID}")
                if not len(samms):
                    logger.error(
                        f"could not find samm with sectionID '{sectionID}' in the db"
                    )
            for samm in samms:
                for c_link in samm.links:
                    doc_id = getattr(c_link.document, "id", None)
                    if not doc_id:
                        continue
                    if doc_id in linked_cre_doc_ids:
                        continue
                    linked_cre_doc_ids.add(doc_id)
                    standard = standard.add_link(
                        defs.Link(
                            document=c_link.document,
                            ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                        )
                    )
        return standard

    def link_to_iso(self, aname, activity, cache, standard):
        linked_iso_doc_ids = {
            l.document.id for l in (standard.links or []) if getattr(l.document, "id", None)
        }
        if not activity.get("references").get("iso27001-2022"):
            logger.error(f"Activity {aname} does not link to ISO")
            return
        for sectionID in activity.get("references").get("iso27001-2022"):
            if sectionID in self.means_none:
                continue
            isos = cache.get_nodes(name="ISO 27001", sectionID=f"{sectionID}")
            if not len(isos):
                logger.error(
                    f"could not find iso with sectionID '{sectionID}' in the db"
                )
                return
            for iso in isos:
                for c_link in iso.links:
                    doc_id = getattr(c_link.document, "id", None)
                    if not doc_id:
                        continue
                    if doc_id in linked_iso_doc_ids:
                        continue
                    linked_iso_doc_ids.add(doc_id)
                    standard = standard.add_link(
                        defs.Link(
                            document=c_link.document,
                            ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                        )
                    )
        return standard

    def parse(
        self,
        cache: db.Node_collection,
        ph: prompt_client.PromptHandler,
    ):
        def extract_from_dsomm(dsomm_obj: dict) -> list[defs.Standard]:
            standard_entries: list[defs.Standard] = []
            for _, dimension in dsomm_obj.items():
                for sname, subdimension in dimension.items():
                    # subdimension is expected to be: {activity_name: activity_dict}
                    if not isinstance(subdimension, dict):
                        continue
                    for aname, activity in subdimension.items():
                        if not isinstance(activity, dict):
                            continue

                        standard = None
                        if activity.get("uuid"):
                            standard = defs.Standard(
                                name=self.name,
                                section=sname,
                                subsection=aname,
                                sectionID=activity.get("uuid"),
                                hyperlink=f"https://dsomm.owasp.org/activity-description?uuid={activity.get('uuid')}",
                                description=(
                                    f"Description:{activity.get('description')}\n"
                                    f" Risk:{activity.get('risk')}\n"
                                    f" Measure:{activity.get('measure')}"
                                ),
                                tags=base_parser_defs.build_tags(
                                    family=base_parser_defs.Family.STANDARD,
                                    subtype=base_parser_defs.Subtype.MATURITY_MODEL,
                                    audience=base_parser_defs.Audience.DEVELOPER,
                                    maturity=base_parser_defs.Maturity.STABLE,
                                    source="owasp_dsomm",
                                    extra=[],
                                ),
                            )
                        else:
                            logger.error(f"Activity {aname} does not have uuid")
                            continue

                        existing = cache.get_nodes(
                            name=standard.name,
                            section=standard.section,
                            sectionID=f"{standard.sectionID}",
                        )
                        if existing:
                            logger.info(
                                f"Node {standard.section} already exists and has embeddings, skipping"
                            )
                            continue

                        if self.manual_mappings.get(aname):
                            cs = cache.get_CREs(self.manual_mappings.get(aname))
                            for c in cs:
                                standard.add_link(
                                    defs.Link(
                                        document=c,
                                        ltype=defs.LinkTypes.AutomaticallyLinkedTo,
                                    )
                                )

                        # use SAMM as Glue
                        refs = activity.get("references") or {}
                        if refs.get("samm2"):
                            standard = self.link_to_samm(activity, cache, standard)
                            if standard:
                                standard_entries.append(standard)
                        else:
                            logger.error(
                                f"Activity {aname} does not link to SAMM, using ISO"
                            )
                            # use iso as glue
                            standard = self.link_to_iso(aname, activity, cache, standard)
                            if standard:
                                standard_entries.append(standard)

            return standard_entries

        # 1) Try legacy aggregated YAML first.
        resp = requests.get(self.LEGACY_GENERATED_YAML_URL, timeout=30)
        if resp.status_code == 200:
            dsomm = yaml.safe_load(resp.text)
            standard_entries = extract_from_dsomm(dsomm)
        else:
            logger.error(
                "Legacy DSOMM YAML missing (status_code=%s); falling back to current multi-file YAML layout.",
                resp.status_code,
            )

            # 2) Fallback: enumerate category YAML files under `src/assets/YAML/default/*/*.yaml`
            # and extract the nested activity structures from each one.
            standard_entries = []
            headers = {"Accept": "application/vnd.github+json"}
            root_items = requests.get(self.GITHUB_API_DEFAULT_YAML_DIR, headers=headers, timeout=30).json()

            for cat in root_items:
                if cat.get("type") != "dir":
                    continue
                cat_path = cat.get("path")
                if not cat_path:
                    continue

                listing_url = (
                    "https://api.github.com/repos/devsecopsmaturitymodel/DevSecOps-MaturityModel-data/contents/"
                    f"{cat_path}?ref=main"
                )
                cat_items = requests.get(listing_url, headers=headers, timeout=30).json()

                for item in cat_items:
                    if item.get("type") != "file":
                        continue
                    name = item.get("name") or ""
                    if not name.endswith(".yaml"):
                        continue
                    if name.startswith("_"):
                        continue

                    download_url = item.get("download_url")
                    if not download_url:
                        continue

                    file_text = requests.get(download_url, headers=headers, timeout=30).text
                    try:
                        dsomm_obj = yaml.safe_load(file_text)
                    except yaml.YAMLError as ye:
                        # Some upstream YAML files contain duplicate anchors which
                        # PyYAML refuses to load (ComposerError). Skip the file
                        # rather than crashing the whole importer.
                        logger.error(
                            "Failed to parse DSOMM YAML file %s (%s); skipping",
                            download_url,
                            str(ye),
                        )
                        continue

                    if isinstance(dsomm_obj, dict):
                        standard_entries.extend(extract_from_dsomm(dsomm_obj))

        results = {self.name: standard_entries}
        base_parser_defs.validate_classification_tags(results)
        return ParseResult(results=results)
