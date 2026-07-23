# OpenCRE FAQ

## What is a CRE?

A **Common Requirement Enumeration (CRE)** is a normalized security requirement in OpenCRE. Standards and guidelines link their sections to CREs so practitioners can see how topics align across sources (OWASP, NIST, ISO, CWE, and others).

Browse top-level CREs from [Root CREs](/root_cres) or open a specific CRE from search results.

## How do I search OpenCRE?

Use the search bar on the [homepage](/) or go to `/search/<term>`. You can search by topic, standard name, CRE id, or free text. The [Chat](/chatbot) page provides an AI assistant grounded in mapped standards content.

## How do I use the REST API?

The public read API is under `/rest/v1/`. Start with:

- [Interactive API reference](/docs#api-reference) on the Docs page
- Raw OpenAPI spec: `/rest/v1/openapi.yaml`

Common examples:

- `GET /rest/v1/id/{creid}` — fetch a CRE by external id
- `GET /rest/v1/standard/{name}` — fetch a standard and its sections
- `GET /rest/v1/text_search?text=...` — free-text search
- `GET /rest/v1/standards` — list known standards

Many endpoints accept `?format=json|md|csv|oscal` for alternate response formats.

## What is Map Analysis?

[Map Analysis](/map_analysis) (gap analysis) shows how two standards relate: shared coverage, unique sections, and linking paths through CREs. Pick two standards in the UI or call `GET /rest/v1/map_analysis?standard=A&standard=B`.

Eligible standards for gap analysis are listed at `GET /rest/v1/ga_standards`.

## Where is the documentation?

- In-app docs: [/docs](/docs)
- Contributing: [docs/CONTRIBUTING.md](https://github.com/OWASP/OpenCRE/blob/main/docs/CONTRIBUTING.md)
- Repository: [github.com/OWASP/OpenCRE](https://github.com/OWASP/OpenCRE)
