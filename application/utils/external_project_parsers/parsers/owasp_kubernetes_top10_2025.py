from cre_logging import get_logger

logger = get_logger(__name__)

from application.utils.external_project_parsers.parsers.owasp_mapping_fixture_parser import (
    OwaspMappingFixtureParser,
)


class OwaspKubernetesTop10_2025(OwaspMappingFixtureParser):
    name = "OWASP Kubernetes Top Ten 2025 (Draft)"
    fixture_name = "owasp_kubernetes_top10_2025"
    fallback_fixture_name = "owasp_kubernetes_top10_2022"
