"""Shared in-memory OIE taxonomy fixtures (mimic tagged Node document_metadata)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any, Dict, List

from application.utils.librarian.oie_taxonomy import TaxonomyIndex

# Minimal seed mirroring what ``oie_tag_standard_sections`` writes onto Nodes.
_FIXTURE_NODES: List[Dict[str, Any]] = [
    {
        "name": "OWASP Top 10 2025",
        "section_id": "A01",
        "section": "Broken Access Control",
        "oie": {
            "version": 2,
            "section_id": "A01",
            "class_id": "access_control",
            "family": "access",
            "standard_family": "appsec",
            "related_classes": [
                "object_authz",
                "function_authz",
                "property_authz",
                "business_flow_abuse",
                "rbac_authz",
            ],
            "transfer": "transfer:top10",
            "phrases": ["access control", "broken access"],
            "standard_hints": ["top 10", "top10", "top_10"],
        },
    },
    {
        "name": "OWASP ASVS",
        "section_id": None,
        "section": "Application Security Verification Standard",
        "oie": {
            "version": 2,
            "section_id": "",
            "class_id": "insecure_design",
            "family": "appsec",
            "standard_family": "appsec",
            "related_classes": [],
            "transfer": "transfer:asvs",
            "phrases": [],
            "standard_hints": ["asvs", "cheat sheet", "cheat_sheet"],
        },
    },
    {
        "name": "OWASP Top 10 2025",
        "section_id": "A02",
        "section": "Security Misconfiguration",
        "oie": {
            "version": 2,
            "section_id": "A02",
            "class_id": "configuration",
            "family": "configuration",
            "standard_family": "appsec",
            "related_classes": ["inventory", "cluster_misconfig"],
            "transfer": "transfer:top10",
            "phrases": ["security misconfigur", "hardening guide"],
            "standard_hints": ["top 10"],
        },
    },
    {
        "name": "OWASP Top 10 2025",
        "section_id": "A05",
        "section": "Injection",
        "oie": {
            "version": 2,
            "section_id": "A05",
            "class_id": "injection",
            "family": "injection",
            "standard_family": "appsec",
            "related_classes": ["ssrf"],
            "transfer": "transfer:top10",
            "phrases": ["sql injection", "xss", "injection"],
            "standard_hints": ["top 10"],
        },
    },
    {
        "name": "OWASP Top 10 2025",
        "section_id": "A07",
        "section": "Authentication Failures",
        "oie": {
            "version": 2,
            "section_id": "A07",
            "class_id": "authentication",
            "family": "auth",
            "standard_family": "appsec",
            "related_classes": ["k8s_authentication", "ai_access_identity"],
            "transfer": "transfer:top10",
            "phrases": ["authentication", "multi-factor", "oauth"],
            "standard_hints": ["top 10"],
        },
    },
    {
        "name": "OWASP API Security Top 10 2023",
        "section_id": "API7",
        "section": "Server Side Request Forgery",
        "oie": {
            "version": 2,
            "section_id": "API7",
            "class_id": "ssrf",
            "family": "ssrf",
            "standard_family": "api",
            "related_classes": ["injection"],
            "transfer": "transfer:api",
            "phrases": ["ssrf", "server-side request"],
            "standard_hints": ["api top", "api security"],
        },
    },
    {
        "name": "OWASP Top 10 for LLM Applications 2025",
        "section_id": "LLM01",
        "section": "Prompt Injection",
        "oie": {
            "version": 2,
            "section_id": "LLM01",
            "class_id": "prompt_injection",
            "family": "ai",
            "standard_family": "ai",
            "related_classes": [
                "system_prompt_leakage",
                "improper_output_handling",
                "excessive_agency",
            ],
            "transfer": "transfer:ai",
            "phrases": ["prompt injection"],
            "standard_hints": ["llm", "aisvs", "genai"],
        },
    },
    {
        "name": "OWASP Top 10 for LLM Applications 2025",
        "section_id": "LLM10",
        "section": "Unbounded Consumption",
        "oie": {
            "version": 2,
            "section_id": "LLM10",
            "class_id": "unbounded_consumption",
            "family": "ai",
            "standard_family": "ai",
            "related_classes": ["resource_consumption", "ai_availability"],
            "transfer": "transfer:ai",
            "phrases": ["unbounded consum"],
            "standard_hints": ["llm", "aisvs"],
        },
    },
    {
        "name": "OWASP Kubernetes Top Ten 2022",
        "section_id": "K08",
        "section": "Secrets Management Failures",
        "oie": {
            "version": 2,
            "section_id": "K08",
            "class_id": "secrets_management",
            "family": "cloud",
            "standard_family": "cloud",
            "related_classes": ["cryptography"],
            "transfer": "transfer:k8s",
            "phrases": ["secrets management", "hashicorp vault"],
            "standard_hints": ["kubernetes", "k8s", "ccm", "csa"],
        },
    },
    {
        "name": "CSA CCM v4",
        "section_id": None,
        "section": "Cloud control",
        "oie": {
            "version": 2,
            "section_id": "",
            "class_id": "cloud_control",
            "family": "cloud",
            "standard_family": "cloud",
            "related_classes": [],
            "transfer": "transfer:k8s",
            "phrases": ["cloud security alliance"],
            "standard_hints": ["ccm", "csa", "cloud sec"],
        },
    },
    {
        "name": "Crypto guidance",
        "section_id": None,
        "section": "Encrypt data at rest with AES",
        "oie": {
            "version": 2,
            "section_id": "",
            "class_id": "cryptography",
            "family": "crypto",
            "standard_family": "appsec",
            "related_classes": ["secrets_management"],
            "transfer": "transfer:top10",
            "phrases": [
                "encrypt data at rest with aes",
                "aes",
                "cryptograph",
                "key management",
            ],
            "standard_hints": ["asvs"],
        },
    },
    {
        "name": "API object authz",
        "section_id": "API1",
        "section": "Broken Object Level Authorization",
        "oie": {
            "version": 2,
            "section_id": "API1",
            "class_id": "object_authz",
            "family": "access",
            "standard_family": "api",
            "related_classes": [
                "access_control",
                "property_authz",
                "function_authz",
            ],
            "transfer": "transfer:api",
            "phrases": ["broken object", "bola", "idor"],
            "standard_hints": ["api top"],
        },
    },
]


def fixture_taxonomy_index() -> TaxonomyIndex:
    nodes = []
    for row in _FIXTURE_NODES:
        nodes.append(
            SimpleNamespace(
                name=row["name"],
                section_id=row.get("section_id"),
                section=row.get("section"),
                metadata_json={"oie": row["oie"]},
            )
        )
    return TaxonomyIndex.from_node_metadata(nodes)
