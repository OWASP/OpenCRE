# OWASP Mapping Fixtures

These JSON files are validation fixtures for OWASP-to-CRE mapping work.

They are intentionally curated and reviewable. They are not the production
OWASP-to-CRE linking path. Production linking is expected to move through the
ETL/librarian pipeline once that path is ready.

## Source snapshots

- `owasp_top10_2025.json`: `https://owasp.org/Top10/2025/`
- `owasp_api_top10_2023.json`: `https://owasp.org/API-Security/editions/2023/en/`
- `owasp_llm_top10_2025.json`: `https://genai.owasp.org/llmrisk/`
- `owasp_aisvs_1_0.json`: `https://github.com/OWASP/AISVS/tree/main/1.0/en`
- `owasp_kubernetes_top10_2022.json`: `https://owasp.org/www-project-kubernetes-top-ten/2022/en/src/`
- `owasp_kubernetes_top10_2025.json`: `https://owasp.org/www-project-kubernetes-top-ten/2025/en/src/`
- `owasp_cheatsheets_supplement.json`: `https://cheatsheetseries.owasp.org/cheatsheets/`

## Dataset notes

- Kubernetes 2025 uses `fallback_section_ids` where 2025 sections consolidate or
  rename 2022 coverage and the fixture needs an explicit review trail.
- `owasp_cheatsheets_supplement.json` is supplemental material for validation and
  does not represent the full OWASP Cheat Sheet Series.
- AISVS links and section names should be treated as provisional review data and
  revalidated against upstream if the project publishes a different canonical
  structure later.

## Known ambiguous mappings

- `owasp_kubernetes_top10_2022.json` currently maps both `K01` and `K09` to the
  same configuration-focused CRE set. This is intentional in the fixture until a
  better `K09`-specific mapping is validated from upstream source material.

## Intended handoff to ETL/librarian work

These fixtures are meant to provide:

- stable section metadata for evaluation
- explicit expected `cre_ids` for selected OWASP resources
- fallback relationships that can be compared against ETL output
- a reviewable record of provisional or ambiguous mappings

Future ETL/librarian integration should treat these files as validation inputs,
not as an importer contract.
