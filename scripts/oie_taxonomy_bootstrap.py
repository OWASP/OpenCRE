#!/usr/bin/env python3
"""One-time bootstrap seed for OIE Node/CRE tagging scripts.

NOT imported by librarian runtime. After rows are tagged into
``document_metadata.oie``, Module C loads classification from the DB only.

Used by ``oie_tag_standard_sections.py`` and ``oie_tag_cre_families.py``.
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple

# Exact Section-ID → (class_id, family). Bootstrapped onto standard Nodes.
SECTION_ID_SEED: Dict[str, Tuple[str, str]] = {
    "A01": ("access_control", "access"),
    "A02": ("configuration", "configuration"),
    "A03": ("supply_chain", "integrity"),
    "A04": ("cryptography", "crypto"),
    "A05": ("injection", "injection"),
    "A06": ("insecure_design", "appsec"),
    "A07": ("authentication", "auth"),
    "A08": ("software_integrity", "integrity"),
    "A09": ("logging_alerting", "logging"),
    "A10": ("exception_handling", "availability"),
    "API1": ("object_authz", "access"),
    "API2": ("authentication", "auth"),
    "API3": ("property_authz", "access"),
    "API4": ("resource_consumption", "availability"),
    "API5": ("function_authz", "access"),
    "API6": ("business_flow_abuse", "access"),
    "API7": ("ssrf", "ssrf"),
    "API8": ("configuration", "configuration"),
    "API9": ("inventory", "configuration"),
    "API10": ("unsafe_api_consumption", "integrity"),
    "LLM01": ("prompt_injection", "ai"),
    "LLM02": ("sensitive_info_disclosure", "ai"),
    "LLM03": ("ai_supply_chain", "ai"),
    "LLM04": ("data_model_poisoning", "ai"),
    "LLM05": ("improper_output_handling", "ai"),
    "LLM06": ("excessive_agency", "ai"),
    "LLM07": ("system_prompt_leakage", "ai"),
    "LLM08": ("vector_embedding_weakness", "ai"),
    "LLM09": ("misinformation", "ai"),
    "LLM10": ("unbounded_consumption", "ai"),
    "K01": ("workload_config", "cloud"),
    "K02": ("k8s_supply_chain", "cloud"),
    "K03": ("rbac_authz", "cloud"),
    "K04": ("policy_enforcement", "cloud"),
    "K05": ("k8s_logging", "cloud"),
    "K06": ("k8s_authentication", "cloud"),
    "K07": ("network_segmentation", "cloud"),
    "K08": ("secrets_management", "cloud"),
    "K09": ("cluster_misconfig", "cloud"),
    "K10": ("vulnerable_components", "cloud"),
    "AISVS1": ("training_data_governance", "ai"),
    "AISVS2": ("ai_input_validation", "ai"),
    "AISVS3": ("model_lifecycle", "ai"),
    "AISVS4": ("ai_infrastructure", "ai"),
    "AISVS5": ("ai_access_identity", "ai"),
    "AISVS6": ("ai_supply_chain", "ai"),
    "AISVS7": ("model_behavior_safety", "ai"),
    "AISVS8": ("ai_privacy", "ai"),
    "AISVS9": ("ai_agency_tooling", "ai"),
    "AISVS10": ("model_context_protocol", "ai"),
    "AISVS11": ("ai_availability", "ai"),
    "AISVS12": ("ai_monitoring", "ai"),
}

# Plain phrases (not regex) written onto Nodes for title/body matching.
PHRASE_SEED: List[Tuple[str, str, str]] = [
    ("prompt injection", "prompt_injection", "ai"),
    ("system prompt", "system_prompt_leakage", "ai"),
    ("model poison", "data_model_poisoning", "ai"),
    ("excessive agency", "excessive_agency", "ai"),
    ("agentic", "excessive_agency", "ai"),
    ("multi-factor", "authentication", "auth"),
    ("mfa", "authentication", "auth"),
    ("webauthn", "authentication", "auth"),
    ("passkey", "authentication", "auth"),
    ("password reset", "authentication", "auth"),
    ("forgot password", "authentication", "auth"),
    ("credential stuff", "authentication", "auth"),
    ("oauth", "authentication", "auth"),
    ("oidc", "authentication", "auth"),
    ("saml", "authentication", "auth"),
    ("session fixation", "authentication", "auth"),
    ("session hijack", "authentication", "auth"),
    ("broken object", "object_authz", "access"),
    ("bola", "object_authz", "access"),
    ("idor", "object_authz", "access"),
    ("broken function", "function_authz", "access"),
    ("bfla", "function_authz", "access"),
    ("rbac", "access_control", "access"),
    ("abac", "access_control", "access"),
    ("least privilege", "access_control", "access"),
    ("access control", "access_control", "access"),
    ("aes", "cryptography", "crypto"),
    ("rsa", "cryptography", "crypto"),
    ("certificate pinning", "cryptography", "crypto"),
    ("key management", "cryptography", "crypto"),
    ("cryptograph", "cryptography", "crypto"),
    ("sql injection", "injection", "injection"),
    ("command injection", "injection", "injection"),
    ("ldap injection", "injection", "injection"),
    ("ssti", "injection", "injection"),
    ("xss", "injection", "injection"),
    ("ssrf", "ssrf", "ssrf"),
    ("server-side request", "ssrf", "ssrf"),
    ("secrets management", "secrets_management", "secrets"),
    ("hashicorp vault", "secrets_management", "secrets"),
    ("credential storage", "secrets_management", "secrets"),
    ("network segment", "network_segmentation", "network"),
    ("network polic", "network_segmentation", "network"),
    ("east-west", "network_segmentation", "network"),
    ("firewall rule", "network_segmentation", "network"),
    ("security logging", "logging_alerting", "logging"),
    ("audit trail", "logging_alerting", "logging"),
    ("siem", "logging_alerting", "logging"),
    ("alerting fail", "logging_alerting", "logging"),
    ("supply chain", "supply_chain", "integrity"),
    ("software integrity", "supply_chain", "integrity"),
    ("security misconfigur", "configuration", "configuration"),
    ("hardening guide", "configuration", "configuration"),
    ("rate limit", "resource_consumption", "availability"),
    ("resource consum", "resource_consumption", "availability"),
    ("denial of service", "resource_consumption", "availability"),
    ("unbounded consum", "resource_consumption", "availability"),
    ("kubernetes", "workload_config", "cloud"),
    ("kube-system", "workload_config", "cloud"),
    ("workload config", "workload_config", "cloud"),
    ("cloud security alliance", "cloud_control", "cloud"),
    ("encrypt data", "cryptography", "crypto"),
]

RELATED_CLASSES_SEED: Dict[str, Tuple[str, ...]] = {
    "access_control": (
        "object_authz",
        "function_authz",
        "property_authz",
        "business_flow_abuse",
        "rbac_authz",
    ),
    "object_authz": ("access_control", "property_authz", "function_authz"),
    "property_authz": ("access_control", "object_authz", "function_authz"),
    "function_authz": ("access_control", "object_authz", "business_flow_abuse"),
    "business_flow_abuse": ("access_control", "function_authz"),
    "authentication": ("k8s_authentication", "ai_access_identity"),
    "k8s_authentication": ("authentication", "ai_access_identity"),
    "cryptography": ("secrets_management",),
    "secrets_management": ("cryptography",),
    "injection": ("ssrf", "ai_input_validation", "improper_output_handling"),
    "ssrf": ("injection",),
    "supply_chain": (
        "software_integrity",
        "k8s_supply_chain",
        "ai_supply_chain",
        "unsafe_api_consumption",
        "vulnerable_components",
    ),
    "software_integrity": ("supply_chain", "k8s_supply_chain", "ai_supply_chain"),
    "k8s_supply_chain": ("supply_chain", "software_integrity", "ai_supply_chain"),
    "ai_supply_chain": ("supply_chain", "software_integrity", "k8s_supply_chain"),
    "configuration": (
        "inventory",
        "cluster_misconfig",
        "workload_config",
        "policy_enforcement",
    ),
    "inventory": ("configuration",),
    "logging_alerting": ("k8s_logging", "ai_monitoring"),
    "k8s_logging": ("logging_alerting", "ai_monitoring"),
    "ai_monitoring": ("logging_alerting", "k8s_logging"),
    "resource_consumption": (
        "unbounded_consumption",
        "exception_handling",
        "ai_availability",
    ),
    "unbounded_consumption": ("resource_consumption", "ai_availability"),
    "exception_handling": ("resource_consumption",),
    "prompt_injection": (
        "system_prompt_leakage",
        "improper_output_handling",
        "excessive_agency",
        "ai_input_validation",
        "ai_agency_tooling",
    ),
    "system_prompt_leakage": ("prompt_injection", "sensitive_info_disclosure"),
    "improper_output_handling": ("prompt_injection", "injection"),
    "excessive_agency": ("prompt_injection", "ai_agency_tooling"),
    "ai_agency_tooling": ("excessive_agency", "prompt_injection"),
    "workload_config": ("cluster_misconfig", "policy_enforcement", "configuration"),
    "cluster_misconfig": ("workload_config", "configuration", "policy_enforcement"),
    "policy_enforcement": ("workload_config", "cluster_misconfig", "rbac_authz"),
    "rbac_authz": ("access_control", "policy_enforcement"),
    "network_segmentation": ("workload_config",),
    "vulnerable_components": ("supply_chain", "k8s_supply_chain"),
    "insecure_design": ("access_control", "configuration"),
}

FAMILY_TO_TRANSFER_SEED: Dict[str, str] = {
    "access": "transfer:top10",
    "auth": "transfer:top10",
    "crypto": "transfer:top10",
    "injection": "transfer:top10",
    "logging": "transfer:top10",
    "integrity": "transfer:top10",
    "configuration": "transfer:top10",
    "availability": "transfer:top10",
    "appsec": "transfer:top10",
    "ssrf": "transfer:api",
    "api": "transfer:api",
    "ai": "transfer:ai",
    "cloud": "transfer:k8s",
    "secrets": "transfer:k8s",
    "network": "transfer:k8s",
}

STANDARD_HINTS_BY_FAMILY: Dict[str, Tuple[str, ...]] = {
    "ai": ("llm", "aisvs", "genai"),
    "cloud": ("kubernetes", "k8s", "ccm", "csa", "cloud sec"),
    "api": ("api top", "api security", "api_top"),
    "appsec": ("asvs", "cheat sheet", "top_10", "top10", "top 10"),
    "gov": ("nist", "iso 270", "pci", "soc 2"),
}

# CRE text → class (bootstrap tagging only).
CRE_CLASS_FROM_TEXT: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(
            r"\b(authenticat\w*|passwords?|sessions?|mfa|oauth|saml|credentials?)\b",
            re.I,
        ),
        "authentication",
    ),
    (
        re.compile(r"\b(authoriz\w*|access\s+control|rbac|privileges?|authz)\b", re.I),
        "access_control",
    ),
    (
        re.compile(
            r"\b(cryptograph\w*|encrypt\w*|tls|certificates?|key\s+manag\w*)\b", re.I
        ),
        "cryptography",
    ),
    (re.compile(r"\b(inject\w*|xss|sqli|csrf|input\s+valid\w*)\b", re.I), "injection"),
    (
        re.compile(r"\b(logg\w*|monitor\w*|audit\w*|alert\w*)\b", re.I),
        "logging_alerting",
    ),
    (re.compile(r"\b(secrets?|vault)\b", re.I), "secrets_management"),
    (re.compile(r"\bssrf\b", re.I), "ssrf"),
    (re.compile(r"\b(supply\s+chain|integrit\w*)\b", re.I), "supply_chain"),
    (re.compile(r"\b(configur\w*|harden\w*)\b", re.I), "configuration"),
    (
        re.compile(r"\b(denial|dos|rate\s+limit\w*|resource\s+consum\w*)\b", re.I),
        "resource_consumption",
    ),
    (
        re.compile(r"\b(prompt\s+inject\w*|model\s+poison\w*|genai|aisvs)\b", re.I),
        "prompt_injection",
    ),
    (re.compile(r"\b(kubernetes|containers?|workloads?)\b", re.I), "workload_config"),
    (re.compile(r"\b(network\s+segment\w*|firewall)\b", re.I), "network_segmentation"),
    (re.compile(r"\b(threat\s+model\w*|architect\w*)\b", re.I), "insecure_design"),
)

CRE_FAMILY_FROM_TEXT: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"\b(authenticat\w*|passwords?|sessions?|mfa|oauth|saml)\b", re.I),
        "auth",
    ),
    (re.compile(r"\b(authoriz\w*|access\s+control|rbac|abac)\b", re.I), "access"),
    (re.compile(r"\b(cryptograph\w*|encrypt\w*|tls|key\s+manag\w*)\b", re.I), "crypto"),
    (re.compile(r"\b(inject\w*|xss|sqli|csrf)\b", re.I), "injection"),
    (re.compile(r"\b(logg\w*|monitor\w*|siem|audit\s+trail)\b", re.I), "logging"),
    (re.compile(r"\b(secrets?|vault)\b", re.I), "secrets"),
    (re.compile(r"\bssrf\b", re.I), "ssrf"),
    (re.compile(r"\b(supply\s+chain|integrit\w*)\b", re.I), "integrity"),
    (re.compile(r"\b(misconfigur\w*|harden\w*)\b", re.I), "configuration"),
    (re.compile(r"\b(prompt\s+inject\w*|genai|aisvs)\b", re.I), "ai"),
    (re.compile(r"\b(kubernetes|k8s|ccm)\b", re.I), "cloud"),
)

CRE_FAMILY_FROM_LINK: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\bASVS\b|Application Security Verification", re.I), "appsec"),
    (re.compile(r"Cheat\s*Sheets?", re.I), "appsec"),
    (re.compile(r"Proactive\s+Controls?", re.I), "appsec"),
    (re.compile(r"Top\s*10", re.I), "appsec"),
    (re.compile(r"API\s*Security|API\s*Top\s*10", re.I), "api"),
    (re.compile(r"\bLLM\b|AISVS|GenAI|AI Security", re.I), "ai"),
    (re.compile(r"Kubernetes|K8s", re.I), "cloud"),
    (re.compile(r"\bCCM\b|Cloud Security Alliance|\bCSA\b", re.I), "cloud"),
    (re.compile(r"NIST|800-53|800-63|\bCSF\b", re.I), "gov"),
    (re.compile(r"ISO\s*270|SOC\s*2|\bPCI\b", re.I), "gov"),
    (re.compile(r"\bSAMM\b|\bCWE\b", re.I), "appsec"),
)

SIBLING_TRANSFER_FROM_LINK: Tuple[Tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"API\s*Security|API\s*Top\s*10", re.I), "transfer:api"),
    (re.compile(r"\bLLM\b|AISVS|GenAI|AI Security", re.I), "transfer:ai"),
    (re.compile(r"Kubernetes|K8s", re.I), "transfer:k8s"),
    (re.compile(r"Top\s*10", re.I), "transfer:top10"),
    (
        re.compile(r"\bASVS\b|Cheat\s*Sheets?|Proactive\s+Controls?", re.I),
        "transfer:asvs",
    ),
)

OIE_META_VERSION = 2

_CLASS_TO_FAMILY: Dict[str, str] = {}
for _cid, _fam in SECTION_ID_SEED.values():
    _CLASS_TO_FAMILY.setdefault(_cid, _fam)
for _ph, _cid, _fam in PHRASE_SEED:
    _CLASS_TO_FAMILY.setdefault(_cid, _fam)


def phrases_for_class(class_id: str) -> List[str]:
    return [p for p, c, _f in PHRASE_SEED if c == class_id]


def normalize_section_id(raw: str) -> str:
    return (raw or "").strip().upper().split(":")[0]


def tag_cre_from_names(
    *,
    cre_name: str,
    description: str,
    linked_names: List[str],
) -> Dict[str, object]:
    """Build verbose ``oie`` metadata block for one CRE (bootstrap / retag)."""
    families: set = set()
    classes: set = set()
    standards: set = set()
    signals: set = set()
    domains: set = set()
    transfers: set = set()

    for link in linked_names:
        for pattern, fam in CRE_FAMILY_FROM_LINK:
            if pattern.search(link or ""):
                families.add(fam)
                standards.add(link.strip()[:80])
                signals.add(f"link:{pattern.pattern[:40]}")
        for pattern, bucket in SIBLING_TRANSFER_FROM_LINK:
            if pattern.search(link or ""):
                transfers.add(bucket)
                signals.add(bucket)
        low = (link or "").lower()
        if "asvs" in low or "cheat" in low:
            domains.add("application")
        if "api" in low:
            domains.add("api")
        if any(x in low for x in ("llm", "aisvs", "genai")):
            domains.add("ai")
        if any(x in low for x in ("kubernetes", "k8s", "ccm", "csa")):
            domains.add("cloud")
        if any(x in low for x in ("nist", "iso", "pci")):
            domains.add("governance")

    blob = f"{cre_name}\n{(description or '')[:400]}"
    for pattern, class_id in CRE_CLASS_FROM_TEXT:
        if pattern.search(blob):
            classes.add(class_id)
            signals.add(f"text_class:{class_id}")
    for pattern, fam in CRE_FAMILY_FROM_TEXT:
        if pattern.search(blob):
            families.add(fam)
            signals.add(f"text_family:{fam}")

    for cid in classes:
        mapped_fam = _CLASS_TO_FAMILY.get(cid)
        if mapped_fam:
            families.add(mapped_fam)

    return {
        "version": OIE_META_VERSION,
        "families": sorted(families),
        "classes": sorted(classes),
        "domains": sorted(domains),
        "standards": sorted(standards)[:12],
        "signals": sorted(signals)[:24],
        "transfers": sorted(transfers),
    }
