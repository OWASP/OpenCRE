from application.database import db
from application.defs import cre_defs as defs
from rq import Queue
from application.utils import redis
from typing import List, Dict, Optional
from application.prompt_client import prompt_client as prompt_client
import logging
import time
from alive_progress import alive_bar
from application.utils.external_project_parsers.parsers import *
from application.utils import gap_analysis

logging.basicConfig()
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# abstract class/interface that shows how to import a project that is not cre or its core resources


class ParserInterface(object):
    # The name of the resource being parsed
    name: str

    def parse(
        database: db.Node_collection,
        prompt_client: Optional[prompt_client.PromptHandler],
    ) -> Dict[str, List[defs.Document]]:
        """
        Parses the resources of a project,
        links the resource of the project to CREs
        this can be done either using glue resources, AI or any other supported method
        then calls cre_main.register_node
        Returns a dict with a key of the resource for importing and a value of list of documents with CRE links, optionally with their embeddings filled in
        """
        raise NotImplementedError


class BaseParser:
    @classmethod
    def register_resource(
        self,
        sclass: ParserInterface,
        db_connection_str: str,
    ):
        from application.cmd import cre_main

        db = cre_main.db_connect(db_connection_str)
        ph = prompt_client.PromptHandler(database=db)
        scalss_instance = sclass()
        result = scalss_instance.parse(db, ph)
        try:
            for _, documents in result.items():
                cre_main.register_standard(documents, db)
        except ValueError as ve:
            err_str = f"error importing {sclass.name}, received 1 value but expected 2"
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
        for subclass in ParserInterface.__subclasses__():
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
