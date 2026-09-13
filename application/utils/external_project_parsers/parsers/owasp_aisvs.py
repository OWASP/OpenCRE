from application.utils.external_project_parsers.parsers.owasp_mapping_fixture_parser import (
    OwaspMappingFixtureParser,
)


class OwaspAisvs(OwaspMappingFixtureParser):
    name = "OWASP AI Security Verification Standard (AISVS)"
    fixture_name = "owasp_aisvs_1_0"
