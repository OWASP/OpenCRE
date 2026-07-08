"""Tests for OpenAPI generation and guardrail."""

from __future__ import annotations

import os
import unittest

from application import create_app
from application.web.openapi_registry import generate_openapi_dict, iter_spec_paths


class OpenApiGuardrailTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ["NO_LOGIN"] = "1"
        self.app = create_app(mode="test")

    def test_generate_openapi_has_public_paths(self) -> None:
        spec = generate_openapi_dict(self.app)
        paths = iter_spec_paths(spec)
        self.assertIn("/rest/v1/standards", paths)
        self.assertIn("/rest/v1/map_analysis", paths)
        self.assertIn("/rest/v1/ga_standards", paths)

    def test_guardrail_script_passes(self) -> None:
        import scripts.check_openapi_guardrail as guardrail

        self.assertEqual(guardrail.main(), 0)


if __name__ == "__main__":
    unittest.main()
