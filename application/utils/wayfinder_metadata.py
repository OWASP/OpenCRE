from typing import Any, Dict, List

# Stable lane ordering for the Wayfinder UI.
SDLC_PHASE_ORDER = [
    "Requirements",
    "Design",
    "Implementation",
    "Verification",
    "Operations",
    "Governance",
    "Training",
    "Uncategorized",
]


def _normalize_name(name: str) -> str:
    return " ".join(str(name or "").replace("_", " ").strip().lower().split())


def _normalize_items(values: List[str]) -> List[str]:
    seen = set()
    result = []
    for value in values or []:
        cleaned = " ".join(str(value).strip().split())
        if not cleaned:
            continue
        lowered = cleaned.lower()
        if lowered in seen:
            continue
        seen.add(lowered)
        result.append(cleaned)
    return result


def _default_metadata(ntype: str) -> Dict[str, Any]:
    normalized_type = str(ntype or "").strip().lower()
    if normalized_type == "tool":
        return {
            "sdlc": ["Implementation", "Verification"],
            "supporting_orgs": ["Unknown"],
            "licenses": ["Unknown"],
            "keywords": ["tooling"],
        }

    if normalized_type == "standard":
        return {
            "sdlc": ["Requirements", "Verification"],
            "supporting_orgs": ["Unknown"],
            "licenses": ["Unknown"],
            "keywords": ["standard"],
        }

    return {
        "sdlc": ["Uncategorized"],
        "supporting_orgs": ["Unknown"],
        "licenses": ["Unknown"],
        "keywords": [],
    }


_ALIASES = {
    "owasp top10 2021": "owasp top 10 2021",
    "owasp top 10": "owasp top 10 2021",
    "pci dss": "pci dss v4.0",
    "devsecops maturity model (dsom)": "devsecops maturity model (dsomm)",
}


_STATIC_METADATA_BY_NAME: Dict[str, Dict[str, Any]] = {
    "asvs": {
        "sdlc": ["Requirements", "Design", "Verification"],
        "supporting_orgs": ["OWASP"],
        "licenses": ["CC BY-SA"],
        "keywords": ["application security verification"],
    },
    "owasp top 10 2021": {
        "sdlc": ["Requirements", "Design", "Verification", "Operations"],
        "supporting_orgs": ["OWASP"],
        "licenses": ["CC BY-SA"],
        "keywords": ["risk awareness", "vulnerability classes"],
    },
    "owasp web security testing guide (wstg)": {
        "sdlc": ["Verification"],
        "supporting_orgs": ["OWASP"],
        "licenses": ["CC BY-SA"],
        "keywords": ["testing guide", "penetration testing"],
    },
    "owasp cheat sheets": {
        "sdlc": ["Design", "Implementation", "Operations"],
        "supporting_orgs": ["OWASP"],
        "licenses": ["CC BY-SA"],
        "keywords": ["implementation guidance"],
    },
    "owasp proactive controls": {
        "sdlc": ["Design", "Implementation"],
        "supporting_orgs": ["OWASP"],
        "licenses": ["CC BY-SA"],
        "keywords": ["secure coding"],
    },
    "samm": {
        "sdlc": [
            "Governance",
            "Requirements",
            "Design",
            "Implementation",
            "Verification",
            "Operations",
            "Training",
        ],
        "supporting_orgs": ["OWASP"],
        "licenses": ["CC BY-SA"],
        "keywords": ["maturity model", "assurance"],
    },
    "owasp wrongsecrets": {
        "sdlc": ["Training", "Implementation"],
        "supporting_orgs": ["OWASP"],
        "licenses": ["MIT"],
        "keywords": ["hands-on", "training"],
    },
    "owasp juice shop": {
        "sdlc": ["Training", "Verification"],
        "supporting_orgs": ["OWASP"],
        "licenses": ["MIT"],
        "keywords": ["ctf", "training", "testing"],
    },
    "zap rule": {
        "sdlc": ["Verification", "Operations"],
        "supporting_orgs": ["OWASP"],
        "licenses": ["Apache-2.0"],
        "keywords": ["dynamic analysis", "scanner"],
    },
    "cwe": {
        "sdlc": ["Design", "Implementation", "Verification"],
        "supporting_orgs": ["MITRE"],
        "licenses": ["Copyright MITRE"],
        "keywords": ["weakness taxonomy"],
    },
    "capec": {
        "sdlc": ["Design", "Verification"],
        "supporting_orgs": ["MITRE"],
        "licenses": ["Copyright MITRE"],
        "keywords": ["attack patterns", "threat modeling"],
    },
    "cloud controls matrix": {
        "sdlc": ["Governance", "Requirements", "Operations"],
        "supporting_orgs": ["Cloud Security Alliance"],
        "licenses": ["CC BY-SA"],
        "keywords": ["cloud controls"],
    },
    "iso 27001": {
        "sdlc": ["Governance", "Requirements", "Operations"],
        "supporting_orgs": ["ISO"],
        "licenses": ["Commercial"],
        "keywords": ["isms", "governance"],
    },
    "nist 800-53 v5": {
        "sdlc": ["Requirements", "Design", "Operations", "Governance"],
        "supporting_orgs": ["NIST"],
        "licenses": ["Public Domain"],
        "keywords": ["security controls"],
    },
    "nist 800-63": {
        "sdlc": ["Requirements", "Design", "Verification"],
        "supporting_orgs": ["NIST"],
        "licenses": ["Public Domain"],
        "keywords": ["digital identity"],
    },
    "nist ssdf": {
        "sdlc": [
            "Requirements",
            "Design",
            "Implementation",
            "Verification",
            "Operations",
            "Governance",
            "Training",
        ],
        "supporting_orgs": ["NIST"],
        "licenses": ["Public Domain"],
        "keywords": ["secure software development framework"],
    },
    "devsecops maturity model (dsomm)": {
        "sdlc": [
            "Governance",
            "Implementation",
            "Verification",
            "Operations",
            "Training",
        ],
        "supporting_orgs": ["OWASP"],
        "licenses": ["CC BY-SA"],
        "keywords": ["devsecops", "maturity model"],
    },
    "pci dss v4.0": {
        "sdlc": ["Requirements", "Verification", "Operations", "Governance"],
        "supporting_orgs": ["PCI SSC"],
        "licenses": ["Commercial"],
        "keywords": ["payment security"],
    },
    "secure headers project": {
        "sdlc": ["Implementation", "Verification", "Operations"],
        "supporting_orgs": ["OWASP"],
        "licenses": ["CC BY-SA"],
        "keywords": ["http headers", "hardening"],
    },
}


def get_wayfinder_metadata(name: str, ntype: str) -> Dict[str, Any]:
    normalized_name = _normalize_name(name)
    canonical_name = _ALIASES.get(normalized_name, normalized_name)
    base_metadata = _STATIC_METADATA_BY_NAME.get(canonical_name)

    if base_metadata is None:
        metadata = _default_metadata(ntype=ntype)
        metadata["source"] = "fallback"
    else:
        metadata = dict(base_metadata)
        metadata["source"] = "static_map"

    metadata["sdlc"] = _normalize_items(metadata.get("sdlc", []))
    metadata["supporting_orgs"] = _normalize_items(metadata.get("supporting_orgs", []))
    metadata["licenses"] = _normalize_items(metadata.get("licenses", []))
    metadata["keywords"] = _normalize_items(metadata.get("keywords", []))

    if not metadata["sdlc"]:
        metadata["sdlc"] = ["Uncategorized"]
    if not metadata["supporting_orgs"]:
        metadata["supporting_orgs"] = ["Unknown"]
    if not metadata["licenses"]:
        metadata["licenses"] = ["Unknown"]

    return metadata
