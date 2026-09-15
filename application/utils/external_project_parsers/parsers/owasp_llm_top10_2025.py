from cre_logging import get_logger

logger = get_logger(__name__)

from application.utils.external_project_parsers.parsers.owasp_mapping_fixture_parser import (
    OwaspMappingFixtureParser,
)


class OwaspLlmTop10_2025(OwaspMappingFixtureParser):
    name = "OWASP Top 10 for LLM and Gen AI Apps 2025"
    fixture_name = "owasp_llm_top10_2025"
