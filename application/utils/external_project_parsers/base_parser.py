from application.utils.external_project_parsers import base_parser_defs
from rq import Queue
from application.utils import redis
from application.prompt_client import prompt_client as prompt_client
import logging
import time
from alive_progress import alive_bar
from application.utils.external_project_parsers.parsers import *
from application.utils import gap_analysis
import os, json

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)


class BaseParser:
    @classmethod
    def register_resource(
        self,
        sclass: base_parser_defs.ParserInterface,
        db_connection_str: str,
    ):
        from application.cmd import cre_main

        db = cre_main.db_connect(db_connection_str)

        ph = prompt_client.PromptHandler(database=db)
        sclass_instance = sclass()

        if os.environ.get("CRE_NO_REIMPORT_IF_EXISTS") and db.get_nodes(
            name=sclass_instance.name
        ):
            logger.info(
                f"Already know of {sclass_instance.name} and CRE_NO_REIMPORT_IF_EXISTS is set, skipping"
            )
            return

        resultObj = sclass_instance.parse(db, ph)
        try:
            for _, documents in resultObj.results.items():
                cre_main.register_standard(
                    standard_entries=documents,
                    db_connection_str=db_connection_str,
                    calculate_gap_analysis=resultObj.calculate_gap_analysis,
                    generate_embeddings=resultObj.calculate_embeddings,
                    collection=db,
                )
        except ValueError as ve:
            err_str = f"error importing {sclass.name}, err: {ve}"
            raise ValueError(err_str)

    def call_importers(self, db_connection_str: str):
        """
        somehow finds all the importers that have been registered (either reflection for implementing classes or an explicit method that registers all available importers)
        and schedules jobs to call those importers, monitors the jobs and alerts when done same as cre_main
        """
        importers = []
        jobs = []
        conn = redis.connect()
        q = Queue(connection=conn)
        import_only = {}
        if os.environ.get("CRE_IMPORTERS_IMPORT_ONLY"):
            import_only = json.loads(os.environ.get("CRE_IMPORTERS_IMPORT_ONLY"))

        for subclass in base_parser_defs.ParserInterface.__subclasses__():
            if import_only and subclass.name not in import_only:
                continue

            importers.append(subclass)
            sclass = subclass

            jobs.append(
                q.enqueue_call(
                    description=sclass.name,
                    func=BaseParser.register_resource,
                    kwargs={
                        "sclass": sclass,
                        "db_connection_str": db_connection_str,
                    },
                    timeout=gap_analysis.GAP_ANALYSIS_TIMEOUT,
                )
            )
        t0 = time.perf_counter()
        total_resources = len(jobs)
        with alive_bar(theme="classic", total=total_resources) as bar:
            redis.wait_for_jobs(jobs=jobs, callback=bar)
        logger.info(
            f"imported {total_resources} standards in {time.perf_counter()-t0} seconds"
        )
        return total_resources
        # TODO(spyros): perhaps it makes sense to abstract the "schedule parser package and monitor" to another method as we're doing this twice
