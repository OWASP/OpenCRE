from application.utils.external_project_parsers.parsers.owasp_mapping_fixture_parser import (
    OwaspMappingFixtureParser,
)


class OwaspTop10_2025(OwaspMappingFixtureParser):
    name = "OWASP Top 10 2025"
    fixture_name = "owasp_top10_2025"
