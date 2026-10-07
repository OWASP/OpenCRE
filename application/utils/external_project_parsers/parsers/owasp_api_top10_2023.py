from cre_logging import get_logger

logger = get_logger(__name__)

from application.utils.external_project_parsers.parsers.owasp_mapping_fixture_parser import (
    OwaspMappingFixtureParser,
)


class OwaspApiTop10_2023(OwaspMappingFixtureParser):
    name = "OWASP API Security Top 10 2023"
    fixture_name = "owasp_api_top10_2023"
