"""Website -> OIE bridge: crawled pages become Module A harvest records.

Contract chain under test: bridge payload -> Module B ChangeRecord (url source)
-> knowledge_queue row -> Module C.0 section, with no LLM in the loop.
"""

from __future__ import annotations

import unittest
from datetime import datetime, timezone

from application import create_app, sqla
from application.database import db
from application.utils.comprehension import external, oie_bridge
from application.utils.librarian.section_validator import section_from_queue_row
from application.utils.comprehension import external_ingest
from application.utils.noise_filter import queue_writer
from application.utils.noise_filter.pipeline import run_noise_filter
from application.utils.noise_filter.schemas import ChangeRecord, ClassifyResult

AT = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
PAGE = "https://slsa.dev/spec/v1.0/levels"
OTHER = "https://slsa.dev/spec/v1.0/requirements"
CHUNKS = [
    (PAGE, 0, "Build L1: provenance exists."),
    (PAGE, 1, "Build L2: the build service signs provenance."),
    (OTHER, 0, "Producer must keep provenance immutable."),
]
TITLES = {PAGE: "SLSA levels", OTHER: "SLSA requirements"}


def _spec() -> external.ExternalSpec:
    return external.ExternalSpec(
        id="slsa", name="SLSA", start_urls=["https://slsa.dev/"]
    )


class PayloadTest(unittest.TestCase):
    def _payloads(self, run="run-1"):
        return oie_bridge.chunks_to_payloads(
            _spec(), CHUNKS, TITLES, run_id=run, fetched_at=AT
        )

    def test_every_payload_is_a_valid_module_b_record(self) -> None:
        payloads = self._payloads()
        self.assertEqual(len(payloads), 3)
        for p in payloads:
            rec = ChangeRecord.model_validate(p)
            self.assertEqual(rec.source.type, "url")
            self.assertEqual(rec.locator.kind, "url")
            self.assertEqual(rec.locator.path, rec.locator.id)

    def test_span_and_headings_are_per_page(self) -> None:
        spans = {
            (p["locator"]["id"], p["span"]["index"]): p["span"]
            for p in self._payloads()
        }
        self.assertEqual(spans[(PAGE, 1)]["total"], 2)
        self.assertEqual(spans[(OTHER, 0)]["total"], 1)
        self.assertEqual(spans[(PAGE, 0)]["heading_path"], ["SLSA levels"])

    def test_ids_are_stable_unique_and_scoped_to_the_site(self) -> None:
        a, b = self._payloads(), self._payloads()
        self.assertEqual([p["chunk_id"] for p in a], [p["chunk_id"] for p in b])
        self.assertEqual(len({p["chunk_id"] for p in a}), 3)
        self.assertTrue(all(p["artifact_id"].startswith("ext-slsa:") for p in a))
        self.assertEqual(a[0]["artifact_id"], a[1]["artifact_id"])  # same page

    def test_url_record_survives_b_and_c0(self) -> None:
        payload = self._payloads()[1]
        rec = ChangeRecord.model_validate(payload)
        item = queue_writer.to_queue_item(
            rec,
            ClassifyResult(label="KNOWLEDGE", confidence=0.9, reasoning="r"),
            "h" * 64,
        )
        self.assertEqual(item.source_type, "url")
        self.assertEqual(item.feed_url, PAGE)
        self.assertIsNone(item.source_repo)
        section = section_from_queue_row(
            {
                **{c.name: getattr(item, c.name) for c in item.__table__.columns},
                "created_at": AT,
            }
        )
        self.assertEqual(section.source.type.value, "url")
        self.assertEqual(str(section.locator.url), PAGE)


class StageTest(unittest.TestCase):
    def setUp(self) -> None:
        self.app = create_app(mode="test")
        self.ctx = self.app.app_context()
        self.ctx.push()
        sqla.create_all()

    def tearDown(self) -> None:
        sqla.session.remove()
        sqla.drop_all()
        self.ctx.pop()

    def _rows(self):
        return sqla.session.query(db.HarvestInput).all()

    def test_stage_writes_pending_rows_without_a_repo(self) -> None:
        payloads = oie_bridge.chunks_to_payloads(
            _spec(), CHUNKS, TITLES, run_id="run-1", fetched_at=AT
        )
        self.assertEqual(oie_bridge.stage_harvest(sqla.session, "run-1", payloads), 3)
        rows = self._rows()
        self.assertEqual({r.status for r in rows}, {"pending"})
        self.assertEqual({r.pipeline_run_id for r in rows}, {"run-1"})
        self.assertTrue(all(r.source_repo is None for r in rows))

    def test_restaging_the_same_run_adds_nothing(self) -> None:
        payloads = oie_bridge.chunks_to_payloads(
            _spec(), CHUNKS, TITLES, run_id="run-1", fetched_at=AT
        )
        oie_bridge.stage_harvest(sqla.session, "run-1", payloads)
        self.assertEqual(oie_bridge.stage_harvest(sqla.session, "run-1", payloads), 0)
        self.assertEqual(len(self._rows()), 3)

    def test_dry_run_writes_nothing(self) -> None:
        payloads = oie_bridge.chunks_to_payloads(
            _spec(), CHUNKS, TITLES, run_id="run-1", fetched_at=AT
        )
        n = oie_bridge.stage_harvest(sqla.session, "run-1", payloads, dry_run=True)
        self.assertEqual(n, 3)
        self.assertEqual(self._rows(), [])

    def test_stage_external_crawls_converts_and_writes(self) -> None:
        class Page:
            def __init__(self, url, title):
                self.url, self.title = url, title

        class Result:
            pages = [Page(PAGE, "SLSA levels"), Page(OTHER, "SLSA requirements")]

        def fake_crawl(spec, max_pages=None, write_cache=True):
            return CHUNKS, Result()

        dry = oie_bridge.stage_external(
            _spec(),
            run_id="r2",
            apply=False,
            session=sqla.session,
            crawl_fn=fake_crawl,
        )
        self.assertEqual((dry["pages"], dry["chunks"], dry["staged"]), (2, 3, 3))
        self.assertEqual(self._rows(), [])
        done = oie_bridge.stage_external(
            _spec(),
            run_id="r2",
            apply=True,
            session=sqla.session,
            crawl_fn=fake_crawl,
        )
        self.assertEqual(done["staged"], 3)
        self.assertEqual(len(self._rows()), 3)

    # ---- the real stages, with a stub classifier ------------------------
    def _stage(self, run="run-e2e"):
        payloads = oie_bridge.chunks_to_payloads(
            _spec(), CHUNKS, TITLES, run_id=run, fetched_at=AT
        )
        oie_bridge.stage_harvest(sqla.session, run, payloads)
        return run

    def test_module_b_filters_pages_and_keepers_reach_c0(self) -> None:
        run = self._stage()

        class Stub:
            # chunks 1 and 3 are security knowledge, chunk 2 (say an events teaser) is not
            def classify_batch(self, records):
                assert len(records) == 3, len(records)
                return [
                    ClassifyResult(label=l, confidence=0.9, reasoning="r")
                    for l in ("KNOWLEDGE", "NOISE", "KNOWLEDGE")
                ]

        summary = run_noise_filter(sqla.session, run, classifier=Stub())
        self.assertEqual((summary.kept_knowledge, summary.inserted), (2, 2))
        rows = sqla.session.query(db.KnowledgeQueueItem).all()
        self.assertEqual({r.source_type for r in rows}, {"url"})
        self.assertTrue(all(r.source_repo is None and r.feed_url for r in rows))
        for row in rows:
            section = section_from_queue_row(row)
            self.assertEqual(section.source.type.value, "url")
        self.assertEqual(
            sqla.session.query(db.HarvestInput).filter_by(status="pending").count(), 0
        )

    def test_ingest_spec_stages_for_oie_only_when_asked(self) -> None:
        class Page:
            def __init__(self, url, title):
                self.url, self.title = url, title

        result = external_ingest.web_source.CrawlResult(
            pages=[Page(PAGE, "SLSA levels"), Page(OTHER, "SLSA requirements")]
        )
        database = db.Node_collection()

        def fake_crawl(spec, max_pages=None, write_cache=True):
            return CHUNKS, result

        plain = external_ingest.ingest_spec(
            _spec(), apply=False, database=database, crawl_fn=fake_crawl
        )
        self.assertNotIn("oie_staged", plain)
        dry = external_ingest.ingest_spec(
            _spec(),
            apply=False,
            database=database,
            oie_run_id="r9",
            crawl_fn=fake_crawl,
        )
        self.assertEqual(dry["oie_staged"], 3)
        self.assertEqual(self._rows(), [])  # dry run writes nothing
        done = external_ingest.ingest_spec(
            _spec(),
            apply=True,
            database=database,
            oie_run_id="r9",
            crawl_fn=fake_crawl,
            write_raw_fn=lambda *args, **kwargs: 3,
        )
        self.assertEqual(done["oie_staged"], 3)
        self.assertEqual(len(self._rows()), 3)


if __name__ == "__main__":
    unittest.main()
